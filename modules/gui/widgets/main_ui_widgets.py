from pathlib import Path
from datetime import datetime, timedelta

from PySide2.QtCore import QObject, QTimer, Slot
from PySide2.QtWidgets import QPushButton

from modules.gui.gui_utils import MouseDblClickFilter
from modules.gui.path_render_service import PathRenderService
from modules.gui.ui_generic_tab import GenericTabWidget
from modules.gui.widgets.path_util import SetDirectoryPath
from modules.gui.widgets.variants_field import VariantInputFields
from modules.gui.widgets.welcome_page import KnechtWelcome
from modules.knecht_render import CPU_COUNT, KnechtRenderThread
from modules.knecht_utils import time_string
from modules.language import get_translation
from modules.log import init_logging
from modules.settings import KnechtSettings

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class MainWindowWidgets(QObject):
    render_calc_timer = QTimer()
    render_calc_timer.setSingleShot(True)
    render_calc_timer.setInterval(1500)

    def __init__(self, ui):
        """ Functionality for MainWindow widgets

        :param modules.gui.main_ui.KnechtWindow ui: MainWindow Widget
        """
        super(MainWindowWidgets, self).__init__(ui)
        self.ui = ui

        # --- Welcome Page ---
        welcome_page = KnechtWelcome(self.ui)
        GenericTabWidget(self.ui, welcome_page)

        # -- Clear Buttons --
        MouseDblClickFilter(self.ui.pushButton_Src_clear, self.clear_document_view)
        MouseDblClickFilter(self.ui.pushButton_delVariants, self.ui.variantTree.clear_tree)
        MouseDblClickFilter(self.ui.pushButton_delRender, self.ui.renderTree.clear_tree)

        # -- Quick View Button --
        self.ui.pushButton_Dest_show: QPushButton
        self.ui.pushButton_Dest_show.toggled.connect(self.toggle_type_filter)

        # -- Sort Tree Buttons --
        self.ui.pushButton_Src_sort.released.connect(self.sort_tab_tree)
        self.ui.pushButton_Var_sort.released.connect(self.ui.variantTree.sort_tree)
        self.ui.pushButton_Ren_sort.released.connect(self.ui.renderTree.sort_tree)

        # ---- Splitter ----
        self.ui.horizontalSplitter.splitterMoved.connect(self.toggle_splitter_labels)
        self.ui.splitterLabelPresets.hide()
        self.ui.splitterLabelVariants.hide()

        # ---- Render Tab ----
        self.ui.renderTree.undo_stack.indexChanged.connect(self.start_render_calc_timer)
        self.render_calc_timer.timeout.connect(self.calculate_render_tree)

        # ---- Setup initial checkbox state and connect to KnechtSettings ---
        self.ui.checkBox_renderTimeout.setChecked(KnechtSettings.dg.get('long_render_timeout'))
        self.ui.checkBox_renderTimeout.toggled.connect(self.render_long_feedback_checkbox)
        self.ui.checkBox_createPresetDir.setChecked(KnechtSettings.app.get('create_preset_dirs'))
        self.ui.checkBox_createPresetDir.toggled.connect(self.render_create_preset_dirs)
        self.ui.checkBox_convertToPng.setChecked(KnechtSettings.app.get('convert_to_png'))
        self.ui.checkBox_convertToPng.toggled.connect(self.render_convert_png)
        self.ui.checkBox_applyBg.setChecked(KnechtSettings.dg.get('viewer_apply_bg'))
        self.ui.checkBox_applyBg.toggled.connect(self.render_apply_viewer_bg)

        # Render Button
        self.ui.pushButton_startRender.pressed.connect(self.start_render_btn)

        # Render calculation description
        self.ui.label_renderTimeDesc.setText(_('Geschätzte Renderzeit ({} CPUs/GI)').format(CPU_COUNT))

        # Render global Output path
        self.render_path = SetDirectoryPath(
            self.ui, mode='dir',
            line_edit=self.ui.lineEdit_currentRenderPath,
            tool_button=self.ui.toolButton_changeRenderPath,
            dialog_args=(_('Ausgabe Verzeichnis auswählen ...'), ),
            reject_invalid_path_edits=True
            )
        self.render_path.set_path(KnechtSettings.app.get('render_path'))
        self.render_path.path_changed.connect(self.render_path_changed)

        # ---- Variant UI functionality ----
        VariantInputFields(ui)

        # ---- Path Render Service ----
        self.path_render_service = PathRenderService(ui.app, ui)

    @Slot()
    def clear_document_view(self):
        view = self.ui.view_mgr.current_view()
        view.clear_tree()

    @Slot()
    def sort_tab_tree(self):
        view = self.ui.view_mgr.current_view()
        view.sort_tree()

    @Slot()
    def toggle_type_filter(self):
        view = self.ui.view_mgr.current_view()
        view.quick_view_filter(self.ui.pushButton_Dest_show.isChecked())

    @Slot()
    def start_render_btn(self):
        # Validate render preset content by collecting variants without reset
        # if no variants collected, deny rendering
        validation_presets = self.ui.renderTree.editor.render.collect_render_presets(collect_reset=False)
        ui_path = Path(self.ui.lineEdit_currentRenderPath.text())
        render_presets = self.ui.renderTree.editor.render.collect_render_presets(global_render_path=ui_path)

        if not render_presets or not validation_presets:
            self.ui.msg(_('Fehler beim sammeln der Preset Varianten. Einige Inhalte der Render Presets '
                          'existieren nicht mehr.'), 8000)
            return
        del validation_presets

        if not self.ui.app.render_dg.is_running():
            self.ui.app.render_dg.start_rendering(render_presets)
        else:
            self.ui.msg(_('Es läuft bereits ein Render Vorgang.'), 5000)

    @Slot(int)
    def start_render_calc_timer(self, undo_index: int):
        self.render_calc_timer.start()

    @Slot()
    def calculate_render_tree(self):
        self.render_calc_timer.stop()
        LOGGER.debug('Render Items changed. Calculating render time.')

        try:
            render_presets = self.ui.renderTree.editor.render.collect_render_presets()
        except Exception as e:
            LOGGER.warning('Error collecting render presets for render time calculation.')
            LOGGER.warning(e)
            return

        rt = KnechtRenderThread(render_presets, Path('.'))
        duration = rt.calculate_remaining_time()
        self.ui.label_renderTime.setText(time_string(duration))

        if duration >= 500.0:
            projected_end = datetime.now() + timedelta(seconds=duration)
            projected_end = projected_end.strftime('%A %d.%m.%Y %H:%M')
            self.ui.label_renderTimeEnd.setText(_('abgeschlossen am: ') + projected_end)

    @Slot(Path)
    def render_path_changed(self, render_path: Path):
        KnechtSettings.app['render_path'] = render_path.absolute().as_posix()

    @Slot(bool)
    def render_create_preset_dirs(self, checked: bool):
        KnechtSettings.app['create_preset_dirs'] = checked

    @Slot(bool)
    def render_convert_png(self, checked: bool):
        KnechtSettings.app['create_preset_dirs'] = checked

    @Slot(bool)
    def render_apply_viewer_bg(self, checked: bool):
        KnechtSettings.dg['viewer_apply_bg'] = checked

    @Slot(bool)
    def render_long_feedback_checkbox(self, checked: bool):
        if not checked:
            KnechtSettings.dg['long_render_timeout'] = False
        elif checked:
            KnechtSettings.dg['long_render_timeout'] = True
            KnechtSettings.dg['check_variants'] = True

    def toggle_splitter_labels(self, pos, index):
        if self.ui.widgetVariants.visibleRegion().isEmpty():
            self.ui.splitterLabelPresets.show()
            self.ui.splitterLabelVariants.hide()
            return

        if self.ui.widgetPresets.visibleRegion().isEmpty():
            self.ui.splitterLabelPresets.hide()
            self.ui.splitterLabelVariants.show()
            return

        self.ui.splitterLabelPresets.hide()
        self.ui.splitterLabelVariants.hide()
