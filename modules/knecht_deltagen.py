import time
from threading import Event, Thread
from typing import Union

from PySide2.QtCore import QObject, QTimer, Signal, Slot, Qt, QUuid
from PySide2.QtGui import QColor
from PySide2.QtWidgets import QComboBox, QPushButton

from modules.globals import DG_TCP_IP, DG_TCP_PORT, DeltaGenResult
from modules.gui.widgets.button_color import QColorButton
from modules.itemview.item import ItemStyleDefaults
from modules.itemview.model import KnechtModel
from modules.itemview.tree_view import KnechtTreeView
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.knecht_plmxml import KnechtPlmXmlController
from modules.knecht_socket import Ncat
from modules.knecht_objects import KnechtVariant, KnechtVariantList
from modules.language import get_translation
from modules.log import init_logging
from modules.settings import KnechtSettings

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class CommunicateDeltaGenSignals(QObject):
    send_finished = Signal(int)
    no_connection = Signal()
    status = Signal(str)
    progress = Signal(int)
    variant_status = Signal(KnechtVariant)


class CommunicateDeltaGen(Thread):
    send_operation_in_progress = False

    # Connection will be terminated if found True
    abort_connection = False

    # Variant List to send
    variants_ls = KnechtVariantList()

    # Command Queue
    command_ls = list()

    # Default Options
    freeze_viewer: bool = True
    check_variants: bool = True
    send_camera_data: bool = True
    long_render_timeout: bool = True
    display_check: bool = False
    viewer_size: str = '1280 720'
    rendering_mode = False

    _regular_receive_timeout = 0.3
    _long_receive_timeout = 1.0

    # --- Signals ---
    signals = CommunicateDeltaGenSignals()

    send_finished = signals.send_finished
    no_connection = signals.no_connection
    status = signals.status
    progress = signals.progress
    variant_status = signals.variant_status

    def __init__(self):
        super(CommunicateDeltaGen, self).__init__()
        # --- External event to end thread ---
        self.exit_event = Event()

        # --- Socket Communication Class ---
        self.nc = Ncat(DG_TCP_IP, DG_TCP_PORT)

    def run(self):
        """ Thread loop running until exit_event set. As soon as a new send operation
            is scheduled, loop will pick up send operation on next loop cycle.
        """
        while not self.exit_event.is_set():
            if self.send_operation_in_progress:
                LOGGER.debug('CommunicateDeltaGen Thread starts Variants Send operation.')
                self._send_operation()
                LOGGER.debug('CommunicateDeltaGen Thread finished Variants Send operation.')

            if self.command_ls:
                # Work down transmitted commands if no send operation active
                self._send_command_operation(self.command_ls.pop(0))

            self.exit_event.wait(timeout=0.8)

        LOGGER.debug('CommunicateDeltaGen Thread returned from run loop.')

    @Slot(bool)
    def set_rendering_mode(self, val: bool):
        """ En-/Disable rendering mode with increased connection timeouts """
        self.rendering_mode = val

    @Slot(KnechtVariantList)
    def set_variants_ls(self, variants_ls: KnechtVariantList):
        self.variants_ls = variants_ls

    @Slot(str)
    def send_command(self, command):
        self.command_ls.append(command)

    @Slot(dict)
    def set_options(self, knecht_dg_settings: dict):
        """ Update the options for the current send operation

        :param KnechtSettings.dg knecht_dg_settings: DeltaGen Settings attribute of KnechtSettings class
        """
        self.freeze_viewer: bool = knecht_dg_settings.get('freeze_viewer')
        self.check_variants: bool = knecht_dg_settings.get('check_variants')
        self.send_camera_data: bool = knecht_dg_settings.get('send_camera_data')
        self.long_render_timeout: bool = knecht_dg_settings.get('long_render_timeout')
        self.display_check: bool = knecht_dg_settings.get('display_variant_check')
        self.viewer_size: str = knecht_dg_settings.get('viewer_size')

    @Slot()
    def start_send_operation(self):
        self.abort_connection = False
        self.send_operation_in_progress = True

    @Slot()
    def abort(self):
        self.abort_connection = True
        LOGGER.info('Abort Signal triggered. Telling send thread to abort.')

    def restore_viewer(self):
        try:
            self.nc.send('SIZE VIEWER ' + self.viewer_size + '; UNFREEZE VIEWER;')
        except Exception as e:
            LOGGER.error('Sending viewer freeze command failed. %s', e)

    def exit_send_operation(self, result: int, skip_viewer: bool = False):
        if self.freeze_viewer and not skip_viewer and not self.rendering_mode:
            self.restore_viewer()

        self.nc.close()
        self.send_finished.emit(result)
        self.send_operation_in_progress = False

    def _connect_to_deltagen(self, timeout=3, num_tries=5):
        """ Tries to establish connection to DeltaGen in num_tries with increasing timeout """
        self.nc.connect()

        if self.rendering_mode:
            timeout, num_tries = 15, 6

        for c in range(0, num_tries):
            if self.nc.deltagen_is_alive(timeout):
                if self.send_operation_in_progress:  # Do not display on command operations
                    self.status.emit(_('DeltaGen Verbindung erfolgreich verifiziert.'))
                return True

            # Next try with slightly longer timeout
            LOGGER.error('Send to DeltaGen thread could not establish a connection after %s seconds.', timeout)
            timeout += c * 2

            if c == num_tries - 1:
                break

            for d in range(6, 0, -1):
                # Check abort signal
                if self.abort_connection:
                    return False

                self.status.emit(_('DeltaGen Verbindungsversuch ({!s}/{!s}) in {!s} Sekunden...')
                                 .format(c + 1, num_tries - 1, d - 1))
                time.sleep(1)

        # No DeltaGen connection, abort
        self.exit_send_operation(DeltaGenResult.send_failed)

        return False

    def _send_command_operation(self, command: str):
        timeout, num_tries = 2, 1

        if self.rendering_mode:
            timeout, num_tries = 20, 5

        if not self._connect_to_deltagen(timeout, num_tries):
            self.no_connection.emit()
            self.exit_send_operation(DeltaGenResult.cmd_failed, skip_viewer=True)
            return

        try:
            self.nc.send(command)
        except Exception as e:
            LOGGER.error('Sending command failed. %s', e)

        self.exit_send_operation(DeltaGenResult.cmd_success, skip_viewer=True)

    def _send_operation(self):
        self.status.emit(_('Prüfe Verbindung...'))

        if not self._connect_to_deltagen():
            self.no_connection.emit()
            self.exit_send_operation(DeltaGenResult.send_failed)
            return

        if self.freeze_viewer:
            self.status.emit(_('Sperre Viewer Fenster'))
            try:
                self.nc.send('SIZE VIEWER 320 240; FREEZE VIEWER;')
            except Exception as e:
                LOGGER.error('Sending freeze_viewer freeze command failed. %s', e)

        # Subscribe to variant states
        self.nc.send('SUBSCRIBE VARIANT_STATE;')

        # Abort signal
        if self.abort_connection:
            self.exit_send_operation(DeltaGenResult.aborted)
            return

        # Send variants
        for idx, variant in enumerate(self.variants_ls.variants):
            time.sleep(0.001)
            self._send_and_check_variant(variant, idx)

            # Abort signal
            if self.abort_connection:
                self.exit_send_operation(DeltaGenResult.aborted)
                return

        self.exit_send_operation(DeltaGenResult.send_success)

    def _send_and_check_variant(self, variant: KnechtVariant, idx, variants_num: int=0):
        """
            Send variant switch command and wait for variant_state EVENT
            variant: VARIANT SET STATE; as string
            idx: List index as integer, identifies the corresponding item in self.variants in thread class
        """
        # Update taskbar progress
        if not variants_num:
            variants_num = len(self.variants_ls)

        __p = round(100 / variants_num * (1 + idx))
        self.progress.emit(__p)

        if variant.item_type == 'command':
            # Look-up new command variants
            variant_str = f'{variant.value};'
        elif variant.item_type == 'camera_command':
            if not self.send_camera_data:
                return
            variant_str = f'{variant.value};'
        else:
            # Extract variant set and value
            variant_str = 'VARIANT {} {};'.format(variant.name, variant.value)

        # Add a long timeout in front of every variant send
        receive_timeout = self._regular_receive_timeout
        if self.long_render_timeout:
            self.nc.deltagen_is_alive(20)
            receive_timeout = self._long_receive_timeout

        # Send variant command
        self.nc.send(variant_str)

        # Check variant state y/n
        recv_str = ''
        if self.check_variants:
            # Receive Variant State Feedback
            recv_str = self.nc.receive(receive_timeout, log_empty=False)

        if recv_str:
            # Feedback should be: 'EVENT variant_state loaded_scene_name variant_idx'
            variant_recv_set, variant_recv_val = '', ''

            # Split into: ['EVENT variant_state scene2 ', 'variant_set', ' ', 'variant_state', '']
            recv_str = recv_str.split('"', 4)
            if len(recv_str) >= 4:
                variant_recv_set = recv_str[1]
                variant_recv_val = recv_str[3]

            # Compare if Feedback matches desired variant state
            if variant_recv_set in variant.name:
                variant.set_name_valid()

            if variant_recv_val in variant.value:
                variant.set_value_valid()

        # Signal results: -index in list-, set column, value column
        self.variant_status.emit(variant)


class SendToDeltaGen(QObject):
    transfer_variants = Signal(KnechtVariantList)
    transfer_options = Signal(dict)
    transfer_command = Signal(str)
    transfer_rendering_mode = Signal(bool)

    restore_viewer_cmd = Signal()
    operation_result = Signal(int)

    abort_operation = Signal()

    active_scene_result = Signal(str, list)  # AsConnector Set/GetActiveScene results

    def __init__(self, ui):
        """ Controls the DeltaGen communication thread.
            Only one, no concurrent, send operations will be allowed.

        :param modules.gui.main_ui.KnechtWindow ui: main gui window
        """
        super(SendToDeltaGen, self).__init__(parent=ui)
        self.ui = ui

        # Keep a reference to finished overlay buttons
        self.finished_queue = list()
        self.finished_queue_size = 5

        # View to display the info overlay
        self.display_view = self.ui.variantTree

        self.rendering = False

        # Setup Main GUI widgets
        self.abort_btn, self.pushButton_Bgr, self.size_box = None, None, None

        self.size_box_timeout = QTimer()
        self.size_box_timeout.setInterval(600)
        self.size_box_timeout.setSingleShot(True)
        self.size_box_timeout.timeout.connect(self.size_viewer)

        self._setup_main_gui()

        # PlmXml Controller
        self.plm_xml_controller = KnechtPlmXmlController(KnechtVariantList())
        self.plm_xml_controller.status.connect(self._update_status)
        self.plm_xml_controller.no_connection.connect(self._no_connection)
        self.plm_xml_controller.send_finished.connect(self._send_operation_finished)
        self.plm_xml_controller.progress.connect(self._update_progress)
        self.plm_xml_controller.plmxml_result.connect(self._plm_xml_finished)
        self.plm_xml_controller.scene_active_result.connect(self._request_active_scene_result)

        # Prepare Send Thread
        self.dg = CommunicateDeltaGen()

        # Prepare thread outbound signals
        self.dg.status.connect(self._update_status)
        self.dg.no_connection.connect(self._no_connection)
        self.dg.send_finished.connect(self._send_operation_finished)
        self.dg.progress.connect(self._update_progress)
        self.dg.variant_status.connect(self._update_variant_status)

        # Prepare thread inbound signals
        self.transfer_variants.connect(self.dg.set_variants_ls)
        self.transfer_options.connect(self.dg.set_options)
        self.transfer_command.connect(self.dg.send_command)
        self.transfer_rendering_mode.connect(self.dg.set_rendering_mode)
        self.abort_operation.connect(self.dg.abort)
        self.restore_viewer_cmd.connect(self.dg.restore_viewer)

        self.dg.start()

    def _display_view_destroyed(self):
        """ If view is closed while sending fall back to variant tree """
        self.display_view = self.ui.variantTree
        self.finished_queue = list()

    def send_variants(self, variant_ls: KnechtVariantList, view: Union[KnechtTreeView, None]=None):
        if self.is_running():
            return

        if view:
            self.display_view = view
            self.display_view.info_overlay.display_exit()
            self.display_view.destroyed.connect(self._display_view_destroyed)
        else:
            self.display_view = self.ui.variantTree

        self.abort_btn.setEnabled(True)
        
        if variant_ls.plm_xml_path is not None:
            self._send_as_connector(variant_ls)
            return
        
        self.transfer_options.emit(KnechtSettings.dg)
        self.transfer_variants.emit(variant_ls)
        self.dg.start_send_operation()
        
    def send_command(self, command: str):
        self.transfer_command.emit(command)

    def send_active_scene_request(self, set_active_scene_name: str=None):
        """ Send a AsConnector Request for a list of available scenes + str of currently active scene
            and, if set, request the provided <set_active_scene_name> to be set as active scene.

            plm_xml_controller.scene_result str, List[str] will be emitted.
            plm_xml_controller.no_connection will be emitted

        :param str set_active_scene_name: Leave blank to just request list of scenes, set to scene name
                                          to request this as active scene
        """
        self.plm_xml_controller.start_get_set_active_scenes(set_active_scene_name)

    def _request_active_scene_result(self, active_scene: str, scenes: list):
        if active_scene and scenes:
            self._update_status(_('AsConnector aktive Szene: {}').format(active_scene))

    def size_viewer(self, size: str=''):
        """ Resize the DeltaGen Viewer with size param or GUI ComboBox setting

        :param[optional] str size: Space separated x y eg. '1920 1080'
        """
        LOGGER.debug('DeltaGen Viewer Size change command.')
        if not size:
            KnechtSettings.dg['viewer_size'] = self.size_box.currentText()
            self.transfer_command.emit('SIZE VIEWER ' + self.size_box.currentText() + '; UNFREEZE VIEWER;')
        else:
            self.transfer_command.emit('SIZE VIEWER ' + size + '; UNFREEZE VIEWER;')

    def set_rendering_mode(self, val: bool=False):
        """ En-/Disable rendering mode with increased connection timeouts """
        self.transfer_rendering_mode.emit(val)
        self.rendering = val

    def is_running(self) -> bool:
        """ Determine wherever a DeltaGen communication thread is running and currently sending variants. """
        if self.dg.is_alive():
            if self.dg.send_operation_in_progress:
                self.ui.msg(_('Es läuft bereits eine DeltaGen Sende Operation! Vorgang abwarten oder abbrechen '
                              'und anschließend erneut versuchen.'))
                LOGGER.info('DeltaGen communication thread is busy! Can not start concurrent send operation.')

                return True
        return False

    def abort(self):
        self.abort_operation.emit()
        self.abort_btn.setEnabled(False)

    def restore_viewer(self):
        self.restore_viewer_cmd.emit()

    def _no_connection(self):
        pass

    def _send_as_connector(self, variant_ls: KnechtVariantList):
        self.plm_xml_controller.variants_ls = variant_ls
        self.plm_xml_controller.start_configuration()

    @Slot(int)
    def _send_operation_finished(self, result: int):
        """ Thread will send result of the send operation """
        self.abort_btn.setEnabled(False)
        self.ui.taskbar_progress.reset()
        self._display_result(result)
        self.operation_result.emit(result)

        if not self.rendering:
            self.ui.app.alert(self.ui, 0)

    def _plm_xml_finished(self, result: str):
        """ Additional PlmXml finished operations, send_operation_finished will also be called """
        def copy_to_clipboard():
            self.ui.app.clipboard().setText(result)

        if self.rendering:
            return

        btns = (
            (_('Kopieren'), copy_to_clipboard),
            ('[X]', None),
            )

        self.display_view.info_overlay.display_confirm(result, btns)

    def _display_result(self, result: int):
        if result == DeltaGenResult.send_success:
            if not self.rendering:
                self.ui.msg(_('DeltaGen Sende Operation beendet.'), 2500)
                self._display_variants_finished_overlay()
        elif result == DeltaGenResult.send_failed:
            self.ui.msg(_('Konnte <b>keine Verbindung</b> '
                          'zu einer DeltaGen Instanz mit geladener Szene herstellen.'), 5000)
        elif result == DeltaGenResult.cmd_success:
            pass
        elif result == DeltaGenResult.cmd_failed:
            self.ui.msg(_('DeltaGen Befehl konnte nicht gesendet werden. <b>Keine Verbindung.</b>'), 5000)
        elif result == DeltaGenResult.aborted:
            self.ui.msg(_('DeltaGen Sende Operation <b>abgebrochen.</b>'), 2500)

    def _update_status(self, message: str, duration: int=2500):
        self.display_view.info_overlay.display(message, duration, True)

    def _update_progress(self, progress: int):
        self.ui.taskbar_progress.setValue(progress)

    def _update_variant_status(self, variant: KnechtVariant):
        msg = _('{0} {1} gesendet').format(variant.name, variant.value)
        self._update_status(msg)

        self._update_tree_view_variant_state(variant)

    def end_thread(self) -> None:
        """ Join the DeltaGen communication thread if active """
        if self.dg.is_alive():
            self.abort_operation.emit()
            self.dg.exit_event.set()
            LOGGER.debug('Joining DeltaGen communication Thread.')
            self.dg.join(timeout=10)

    def _setup_main_gui(self):
        """ Setup the quick access controls in MainWindow """
        self.abort_btn: QPushButton = self.ui.pushButton_abort
        self.abort_btn.released.connect(self.abort)

        # -- Viewer Background Color ---
        self.pushButton_Bgr: QColorButton = self.ui.pushButton_Bgr
        self.pushButton_Bgr.set_color_from_string(KnechtSettings.dg['viewer_background'])
        self.pushButton_Bgr.colorChanged.connect(self._update_viewer_color)

        # -- Viewer Size ---
        self.size_box: QComboBox = self.ui.comboBox_ViewerSize
        for idx in range(0, self.size_box.count()):
            item_text = self.size_box.itemText(idx)
            if item_text == KnechtSettings.dg['viewer_size']:
                self.size_box.setCurrentIndex(idx)
                break

        self.size_box.currentIndexChanged.connect(self._size_viewer_combo_box_start)

    def apply_viewer_bg_color(self):
        """ Apply the currently color button color to the DG Viewer """
        color = self.pushButton_Bgr.color()
        self._update_viewer_color(color)

    @Slot(QColor)
    def _update_viewer_color(self, color: QColor):
        KnechtSettings.dg['viewer_background'] = color.name()
        c = (color.redF(), color.greenF(), color.blueF(), color.alphaF())
        color_cmd = 'BACKGROUND VIEWER {:.4f} {:.4f} {:.4f} {:.4f};'.format(*c)
        self.transfer_command.emit(color_cmd)

    def _size_viewer_combo_box_start(self):
        self.size_box_timeout.start()

    def _display_variants_finished_overlay(self):
        """ Display a message with last send variants preset and provide option to select it """
        if not self.dg.variants_ls.preset_name or not KnechtSettings.dg.get('display_send_finished_overlay'):
            return

        preset_selector = _OverlayPresetSelector(
            self.display_view, self.dg.variants_ls.preset_id, self.dg.variants_ls.preset_name
            )
        self.finished_queue.insert(0, preset_selector)
        self.finished_queue = self.finished_queue[:self.finished_queue_size]

    def _update_tree_view_variant_state(self, variant: KnechtVariant):
        src_model: KnechtModel = self.display_view.model().sourceModel()
        name_idx = variant.index.siblingAtColumn(Kg.NAME)
        value_idx = variant.index.siblingAtColumn(Kg.VALUE)

        src_model.setData(name_idx, ItemStyleDefaults.variant_default_color, Qt.BackgroundRole)
        src_model.setData(value_idx, ItemStyleDefaults.variant_default_color, Qt.BackgroundRole)

        if not KnechtSettings.dg.get('display_variant_check'):
            return

        name_color, value_color = ItemStyleDefaults.variant_invalid_color, ItemStyleDefaults.variant_invalid_color

        if variant.name_valid:
            name_color = ItemStyleDefaults.variant_valid_color
        if variant.value_valid:
            value_color = ItemStyleDefaults.variant_valid_color

        src_model.setData(name_idx, name_color, Qt.BackgroundRole)
        src_model.setData(value_idx, value_color, Qt.BackgroundRole)


class _OverlayPresetSelector:
    def __init__(self, view: KnechtTreeView, preset_id: QUuid, preset_name: str):
        """ Helper class to select the preset from the last send operation """
        self.view = view
        self.preset_id = preset_id

        btns = (
            (_('Auswählen'), self.select_preset),
            ('[X]', None)
            )
        self.view.info_overlay.display_confirm(
            _('Senden an DeltaGen abgeschlossen:<br /><i>{}</i>').format(preset_name), btns)

    def select_preset(self):
        item = self.view.model().sourceModel().id_mgr.get_preset_from_id(self.preset_id)
        if item:
            idx = self.view.model().sourceModel().get_index_from_item(item)
            self.view.editor.selection.clear_and_select_src_index_ls([idx])
