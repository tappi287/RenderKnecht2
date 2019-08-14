import math
import multiprocessing
import time
from datetime import datetime
from pathlib import Path
from threading import Thread
from typing import List

from PySide2.QtCore import QObject, Qt, Signal, Slot
from imageio import imread

from modules.gui.widgets.message_box import GenericErrorBox
from modules.gui.widgets.path_util import path_exists
from modules.itemview.tree_view import KnechtTreeView
from modules.knecht_deltagen import CommunicateDeltaGen, SendToDeltaGen
from modules.knecht_image import KnechtImage
from modules.knecht_utils import time_string
from modules.knecht_objects import KnechtRenderPreset, KnechtVariantList
from modules.language import get_translation
from modules.log import init_logging
from modules.settings import KnechtSettings

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext

# Render Calculation
# 1280px x will be 1, 2560px x will be 2 @NeMo4:3
RENDER_RES_FACTOR = 0.00078125
# Machine with 72 cores @2,4GHz, 12 cores @4GHz would be 0,004
RENDER_MACHINE_FACTOR = 0.00105
# RenderTime would be
# render_time = (resolution_x * sampling) * RENDER_MACHINE_FACTOR * (resolution_x * RENDER_RES_FACTOR)
CPU_COUNT = multiprocessing.cpu_count()


def calculate_render_time(render_preset: KnechtRenderPreset) -> float:
    """ Calculate Render Time per Image in float seconds """
    LOGGER.debug('Calculating render time with %s CPUs', CPU_COUNT)

    if CPU_COUNT > 1 and CPU_COUNT != 72:
        # CPU guessed as Workstation with slow, but many cores CPU @~2.4GHz
        cpu_factor = (1-0.003)/12 * (1-0.001) / CPU_COUNT
    else:
        # If ideal thread count is undetected, it will return 1
        # We will assume a machine with 72 cores @~2.4GHz
        cpu_factor = RENDER_MACHINE_FACTOR
    if CPU_COUNT == 12:
        # We exactly know the speed of current gen 12c CPUs @~4GHz
        cpu_factor = 0.004

    try:
        res_x = int(render_preset.settings.get('resolution').split(' ')[0])
        sampling = int(render_preset.settings.get('sampling'))
    except Exception as e:
        LOGGER.error('Error getting settings for render calculation. Using default values 1280 512\n%s', e)
        res_x, sampling = 1280, 512

    res_factor = res_x * RENDER_RES_FACTOR
    sample_factor = res_x * sampling

    return sample_factor * cpu_factor * res_factor


class KnechtRenderSignals(QObject):
    status = Signal(str)
    progress = Signal(int)
    progress_text = Signal(str)
    finished = Signal(int)
    aborted = Signal()
    btn_text = Signal(str)
    viewer_color = Signal()
    render_time = Signal(str)
    error = Signal(str)

    send_variants = Signal(KnechtVariantList)
    send_command = Signal(str)


class KnechtRenderThread(Thread):
    command = dict(
        # IMAGE_SAA_QUALITY VIEWER 12;
        sampling='IMAGE_SAA_QUALITY VIEWER ',

        # IMAGE "C:\path\img_file.ext" 1280 720;'
        render='IMAGE ',
        )
    wait_timeout = 1800  # 30 minutes general timeout
    render_timeout = 10800  # 3 hours rendering timeout

    render_log_msg = [_('RenderKnecht Render Log erstellt am '),
                      _('Erzeuge Bild mit Namen:'),
                      _('Varianten:')]

    long_render_timeout = False
    create_preset_dirs = False
    convert_to_png = True
    apply_viewer_bg = False

    # --- Signals ---
    signals = KnechtRenderSignals()

    status = signals.status
    progress = signals.progress
    progress_text = signals.progress_text
    btn_text = signals.btn_text
    render_time = signals.render_time
    send_variants = signals.send_variants
    send_command = signals.send_command
    finished = signals.finished
    aborted = signals.aborted
    error = signals.error
    viewer_color = signals.viewer_color

    class Result:
        rendering_completed = 0
        rendering_aborted = 1
        rendering_failed = 2
        not_set = -1

    def __init__(self, render_presets: List[KnechtRenderPreset], global_render_path: Path=Path('.')):
        super(KnechtRenderThread, self).__init__()
        self.render_presets = render_presets[::]
        self.global_render_path = global_render_path
        self.render_log = str()
        self.render_log_name = 'RenderKnecht_Log_'

        self.rendered_img_count = 0
        self.render_result = self.Result.not_set

        self.render_start_time = 0.0
        self.render_total_time = 0.0
        self.current_img_start_time = 0.0
        self.current_img_render_time = 0.0

        self.abort_rendering = False

        self.long_render_timeout = KnechtSettings.dg.get('long_render_timeout')
        self.create_preset_dirs = KnechtSettings.app.get('create_preset_dirs')
        self.convert_to_png = KnechtSettings.app.get('convert_to_png')
        self.apply_viewer_bg = KnechtSettings.dg.get('viewer_apply_bg')

        self.img_thread = KnechtImage()
        self.img_thread.conversion_result.connect(self._image_conversion_result)
        self.img_conversion_finished = False

        self.dg_operation_finished = False
        self.dg_operation_result = -1

    def run(self):
        if self.verify_render_presets():
            self.render_loop()
        else:
            self.render_result = self.Result.rendering_failed

        self.finish_rendering()
        LOGGER.info('Rendering Thread finished.')

    def verify_render_presets(self) -> bool:
        """ Verify the rendering settings before start """
        # --- Verify path lengths and output path set ---
        too_long_paths, invalid_paths = list(), list()

        for render_preset in self.render_presets:
            render_preset.create_preset_dir = self.create_preset_dirs

            # --- Verify Path length and try to create output directories
            if not render_preset.verify_path_lengths():
                too_long_paths += [p.name for p in render_preset.too_long_paths]
            else:
                # At this point output directories will be created
                if not render_preset.verify_output_paths():
                    invalid_paths += render_preset.invalid_paths

            # --- Verify Render Preset Resolution
            #     (the only field were user input is possible)
            setting_result = True
            try:
                res_values = [int(r) for r in render_preset.settings.get('resolution').split(' ')]
                if len(res_values) != 2 or sum(res_values) < 0 or sum(res_values) > 99999:
                    setting_result = False
            except ValueError or TypeError as e:
                # Resolution settings does not contain integers
                LOGGER.error(e)
                setting_result = False

            if not setting_result:
                self.error.emit(_('Ungültige Auflösungseinstellungen in {}').format(render_preset.name))
                return False

        if too_long_paths:
            self.error.emit(
                _('Die folgenden Ausgabepfade sind zu lang, Rendering wird abgebrochen. {}{}'
                  ).format('\n\n', '\n'.join(too_long_paths))
                )
            return False

        if invalid_paths:
            self.error.emit(_('Die Render Presets enthalten ungültige Ausgabepfade. '
                              'Rendering wird abgebrochen. {}{}').format('\n\n', '\n'.join(invalid_paths))
                            )
            return False

        return True

    def render_loop(self):
        self.render_total_time = self.calculate_remaining_time()
        self.render_time.emit(time_string(self.render_total_time))
        self.progress.emit(1)

        self.render_start_time = time.time()

        for render_preset in self.render_presets:
            self._init_render_log(render_preset)

            # Render images
            while render_preset.remaining_images():
                if self.abort_rendering:
                    return

                name, variant_ls, img_out_dir = render_preset.get_next_render_image()
                self.render_image(name, variant_ls, render_preset, img_out_dir)

                if self.abort_rendering:
                    return

                self._write_render_log(img_out_dir)

        if self.rendered_img_count >= self.total_image_count():
            duration = time_string(time.time() - self.render_start_time)
            self.progress_text.emit(_('{} Rendering von {} Bildern abgeschlossen in {}').format(
                datetime.now().strftime('%A %H:%M -'), self.total_image_count(), duration))
            self.render_result = self.Result.rendering_completed

    def render_image(self, name: str, variant_ls: KnechtVariantList, render_preset: KnechtRenderPreset, out_dir: Path):
        """ perform rendering for the current image """
        self.current_img_start_time = time.time()
        self.current_img_render_time = calculate_render_time(render_preset)

        # Update Progress
        progress_name = name
        if len(progress_name) >= 60:
            progress_name = progress_name[:50] + ' ~ ' + progress_name[-11:]
        self.progress_text.emit(f'{progress_name} - {self.rendered_img_count + 1:02d}/{self.total_image_count():02d}')

        # --- Send image variants
        self.send_variants.emit(variant_ls)
        self.btn_text.emit(_('Sende Varianten...'))
        if not self._await_dg_result():
            self.abort_no_connection()
            return

        # --- Set Sampling Setting
        sample_level = self.get_samples(render_preset.settings.get('sampling'))
        self.send_command.emit(
            f'{self.command.get("sampling")}{sample_level}'
            )
        self.btn_text.emit(_('Sende Einstellungen...'))
        if not self._await_dg_result():
            self.abort_no_connection()
            return

        # --- Apply viewer bg color
        if self.apply_viewer_bg:
            self.viewer_color.emit()
            self._await_dg_result()

        # --- Send Rendering command
        # Create img file name and final output path
        img_file_name = f'{name}{render_preset.settings.get("file_extension")}'
        img_path = out_dir / img_file_name

        if self.abort_rendering:
            return

        # Actual render command
        self.send_command.emit(
            f'IMAGE "{img_path.absolute().as_posix()}" {render_preset.settings.get("resolution")}'
            )
        self._await_dg_result()

        # --- Loop until image created
        LOGGER.info('Rendering image: %s', img_path.name)
        self.render_log += f'\n\n{self._return_date_time()} {self.render_log_msg[1]} {name}\n{self.render_log_msg[2]}\n'
        self._add_variants_log(variant_ls)

        self._await_rendered_image(img_path)

        # --- Convert result image to PNG
        if self.convert_to_png and render_preset.settings.get("file_extension") != '.png':
            if self.img_thread.convert_file(img_path, out_dir, move_converted=True):
                msg = _('Konvertiere Bilddaten...')
                self.status.emit(msg)
                self.btn_text.emit(msg)
                self._await_conversion_result()

        self.rendered_img_count += 1

        return img_path.absolute()

    def finish_rendering(self):
        self.btn_text.emit(_('Rendering starten'))

        self.finished.emit(self.render_result)

    def display_remaining_time(self):
        remaining = self.calculate_remaining_time()

        img_time_elapsed = time.time() - self.current_img_start_time
        img_progress = img_time_elapsed * 100 / max(1.0, self.current_img_render_time)
        self.progress.emit(img_progress)

        self.btn_text.emit(time_string(remaining))

    def _await_dg_result(self) -> bool:
        """ Wait until Dg send operation finished -> return True on successful send """
        start_time = time.time()
        while not self.dg_operation_finished:
            time.sleep(1)

            if self.abort_rendering:
                break

            if self._is_timed_out(start_time, self.wait_timeout):
                break

        result = True
        c = CommunicateDeltaGen.Result
        if self.dg_operation_result not in [c.send_success, c.cmd_success]:
            result = False

        self.dg_operation_finished = False
        self.dg_operation_result = -1
        return result

    def _await_rendered_image(self, img_path: Path):
        """ Wait until image was created """
        start_time = time.time()
        while not path_exists(img_path):
            time.sleep(1)

            self.display_remaining_time()

            if self.abort_rendering:
                return

            if self._is_timed_out(start_time, self.render_timeout):
                break

        # Leave some time for DG to write the image
        time.sleep(3)

        # Verify a valid image file was created
        self.status.emit(_('Prüfe Bilddaten...'))
        self.btn_text.emit(_('Prüfe Bilddaten...'))
        self.verify_rendered_image(img_path)

        # Image created
        self.status.emit(_('Rendering erzeugt.'))
        self.btn_text.emit(_('Rendering erzeugt.'))
        time.sleep(0.5)

        # Wait 5 seconds for DeltaGen to recover
        for count in range(5, 0, -1):
            msg = _('Erzeuge nächstes Bild in {}...').format(str(count))
            self.status.emit(msg + '\n')
            self.btn_text.emit(msg)
            time.sleep(1)

    def _await_conversion_result(self):
        """ Wait until image conversion thread finished """
        start_time = time.time()
        while not self.img_conversion_finished:
            time.sleep(1)

            if self.abort_rendering:
                break

            if self._is_timed_out(start_time, self.wait_timeout):
                break

        self.img_conversion_finished = False

    @staticmethod
    def _return_date_time(only_minutes=False):
        date_msg = time.strftime('%Y-%m-%d')
        time_msg = time.strftime('%H:%M:%S')

        if only_minutes:
            return time_msg
        else:
            return date_msg + ' ' + time_msg

    @staticmethod
    def _is_timed_out(start_time, timeout) -> bool:
        if time.time() - start_time > timeout:
            return True
        return False

    @Slot(str)
    def _image_conversion_result(self, result: str):
        self.render_log += _('Bild Konvertierung: {}').format(result)
        self.img_conversion_finished = True

    @Slot(int)
    def dg_result(self, result: int):
        self.dg_operation_result = result
        self.dg_operation_finished = True

    def abort_no_connection(self):
        self.error.emit(_('Render Vorgang abgebrochen.{}Konnte keine Verbindung zu einer '
                          'DeltaGen Instanz herstellen.').format('\n\n'))
        self.abort()
        self.render_result = self.Result.rendering_failed

    @Slot()
    def abort(self):
        self.render_result = self.Result.rendering_aborted
        self.abort_rendering = True
        self.aborted.emit()

    def verify_rendered_image(self, img_path: Path, timeout=3300):
        """ Read rendered image with ImageIO to verify as valid image or break after 55mins/3300secs """
        begin = time.time()
        img = False
        exception_message = ''

        if self.long_render_timeout:
            # Long render timeout eg. A3 can take up to 40min to write an image
            # wait for 30min / 1800sec
            timeout = 1800

        while 1:
            if self.abort_rendering:
                return

            try:
                # Try to read image
                with open(img_path.as_posix(), 'rb') as f:
                    img = imread(f)
                img = True
            except ValueError or OSError as exception_message:
                """ Value error if format not found or file incomplete; OSError on non-existent file """
                LOGGER.debug('Rendered image could not be verified. Verification loop %s sec.\n%s', timeout,
                             exception_message)

                # Display image verification in Overlay
                self.status.emit(_('Bilddaten konnten nicht als gültiges Bild verifiziert werden.{}'
                                   ).format(f'\n{img_path.name}'))

                # Wait 10 seconds
                time.sleep(10)

            if img:
                del img
                LOGGER.debug('Rendered image was verified as valid image file.')

                # Display image verification in Overlay
                try:
                    msg = _('Bilddaten wurden erfolgreich verifiziert: {}').format(f'{img_path.name}\n')
                    self.status.emit(msg)
                except Exception as e:
                    LOGGER.error('Tried to send overlay error message. But:\n%s', e)

                break

            # Timeout
            if time.time() - begin > timeout:
                LOGGER.error('Rendered image could not be verified as valid image file after %s seconds.', timeout)
                self.render_log += _('{0}Datei konnte nicht als gültige Bilddatei verfiziert werden: {1}{0}'
                                     ).format('\n', img_path)

                try:
                    if exception_message:
                        self.render_log += exception_message + '\n'
                except UnboundLocalError:
                    # exception_message not defined
                    pass

                break

    def update_preset_dirs(self, out_dir):
        """ Update render preset output directorys """
        if not self.create_preset_dirs:
            return

        for render_preset in self.render_presets:
            render_preset.path = render_preset.path / render_preset.name

    @staticmethod
    def get_samples(sampling: str) -> int:
        """
        Reverse actual sampling value to sampling level 1-12

        :param str sampling: string value between 1 - 4096, should be power of 2 eg. 64, 512, 1024 etc.
        :return:
        """
        sampling = int(sampling)

        # Reverse power of two
        sample_pow = math.log(max(1, sampling)) / math.log(2)

        # Clamp 0 - 12 and round to int
        sampling_level = max(1, min(12, int(sample_pow)))

        return sampling_level

    def _init_render_log(self, render_preset: KnechtRenderPreset):
        self.render_log_name = 'RenderKnecht2_Log_' + str(time.time()) + '.log'
        self.render_log = ''
        self.render_log += self.render_log_msg[0] + self._return_date_time() + '\n\n'

        self.render_log += _('{} Einstellungen - ').format(render_preset.name)
        self.render_log += _('Sampling: {} - Res: ').format(render_preset.settings.get('sampling'))
        self.render_log += _('{}px - Ext: ').format(render_preset.settings.get('resolution').replace(' ', 'x'))
        self.render_log += '{}'.format(render_preset.settings.get('file_extension'))

    def _write_render_log(self, img_out_dir: Path):
        try:
            with open(Path(img_out_dir / self.render_log_name), 'w') as e:
                print(self.render_log, file=e)
        except Exception as e:
            LOGGER.error('Error writing render log to file: %s', e)

    def _add_variants_log(self, variant_ls: KnechtVariantList):
        for variant in variant_ls.variants:
            self.render_log += '{} {};'.format(variant.name, variant.value)

        self.render_log += '\n\n'

    def total_image_count(self):
        """ Return total number of images that need to be rendered """
        img_num = 0
        for render_preset in self.render_presets:
            img_num += render_preset.image_count()

        return img_num

    def calculate_remaining_time(self):
        """ Return the total remaining time for all images since render start in float seconds """
        if self.render_start_time:
            time_elapsed = time.time() - self.render_start_time
        else:
            time_elapsed = 0.0

        render_time = 0.0

        for render_preset in self.render_presets:
            img_time: float = calculate_render_time(render_preset)

            if render_preset.current_image_number():
                # Render preset in progress, add the currently rendering image to render time
                render_time += img_time * (1 + render_preset.remaining_images())
            else:
                # Render preset not yet started, only calculate remaining
                render_time += img_time * render_preset.remaining_images()

        return max(0.0, render_time - time_elapsed)


class KnechtRender(QObject):
    _abort_rendering = Signal()

    def __init__(self, ui):
        """
        Create and start a thread to render images

        :param modules.gui.main_ui.KnechtWindow ui:
        """
        super(KnechtRender, self).__init__(parent=ui)
        self.ui = ui

        self.ui.progressBar_render.setAlignment(Qt.AlignCenter)
        self.ui.progressBar_render.setMaximum(100)

        # Communicate to DeltaGen via app Dg thread controller
        self.send_dg: SendToDeltaGen = self.ui.app.send_dg

        # View to display the info overlay
        self.display_view: KnechtTreeView = self.ui.renderTree

        # Rendering Thread
        self.rt = KnechtRenderThread(list(), Path('.'))

        # Prepare thread outbound signals
        self.rt.status.connect(self._update_status)
        self.rt.progress.connect(self._update_progress)
        self.rt.progress_text.connect(self._update_progress_text)
        self.rt.btn_text.connect(self._update_btn_text)
        self.rt.error.connect(self._display_rendering_error)
        self.rt.render_time.connect(self._update_render_time_display)

        self.rt.send_variants.connect(self.dg_send_variants)
        self.rt.send_command.connect(self.dg_send_command)

        self.rt.finished.connect(self.finish_rendering)
        self.rt.aborted.connect(self.rendering_aborted)
        self.rt.viewer_color.connect(self.send_dg.apply_viewer_bg_color)

        # Connect GUI Elements
        self.ui.pushButton_abortRender.released.connect(self.abort)

        self.error_message_box = GenericErrorBox(self.ui)

    def start_rendering(self, render_presets: List[KnechtRenderPreset]):
        self.send_dg.set_rendering_mode(True)
        self.ui.pushButton_abortRender.setEnabled(True)

        # Render Thread
        self.rt = KnechtRenderThread(render_presets)

        # Prepare thread inbound signals
        self._abort_rendering.connect(self.rt.abort)
        self.send_dg.operation_result.connect(self.rt.dg_result)

        self.rt.start()

    @Slot(int)
    def finish_rendering(self, result: int=KnechtRenderThread.Result.not_set):
        self.send_dg.set_rendering_mode(False)
        self.send_dg.restore_viewer()

        self._update_progress(0)
        self.ui.progressBar_render.setTextVisible(False)

        self.ui.pushButton_abortRender.setEnabled(False)

        if result == KnechtRenderThread.Result.rendering_completed:
            LOGGER.info('Rendering completed.')
            self.ui.progressBar_render.setTextVisible(True)
            self.ui.show_tray_notification(_('Renderliste'), self.ui.progressBar_render.text())
            self.ui.app.alert(self.ui, 0)
            self.ui.play_finished_sound()

    @Slot()
    def rendering_aborted(self):
        """ Render Thread sent abort signal """
        self.send_dg.abort()
        self.finish_rendering()

    @Slot(KnechtVariantList)
    def dg_send_variants(self, variants: KnechtVariantList):
        self.send_dg.send_variants(variants, self.ui.renderTree)

    @Slot(str)
    def dg_send_command(self, command: str):
        self.send_dg.send_command(command)

    def is_running(self) -> bool:
        """ Determine wherever a DeltaGen render thread is running. """
        if self.rt.is_alive():
            return True
        return False

    def abort(self):
        self._abort_rendering.emit()
        self.send_dg.abort()
        self.ui.pushButton_abortRender.setEnabled(False)

    @Slot(str)
    def _display_rendering_error(self, txt: str):
        self.error_message_box.setWindowTitle(_('Rendering'))
        self.error_message_box.set_error_msg(txt)
        self.ui.play_warning_sound()
        self.ui.app.alert(self.ui, 8000)

        self.error_message_box.exec_()

    @Slot(str)
    def _update_render_time_display(self, txt: str):
        self.ui.label_renderTime.setText(txt)

    @Slot(str)
    def _update_btn_text(self, txt: str):
        self.ui.pushButton_startRender.setText(txt)

    @Slot(str, int)
    def _update_status(self, message: str, duration: int=800):
        self.display_view.info_overlay.display(message, duration, True)

    @Slot(str)
    def _update_progress_text(self, text: str):
        self.ui.progressBar_render.setFormat(text)
        self.ui.progressBar_render.setTextVisible(True)

    @Slot(int)
    def _update_progress(self, value):
        self.ui.progressBar_render.setValue(value)
        self.ui.taskbar_progress.setValue(round(value))
