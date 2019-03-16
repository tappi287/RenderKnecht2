from pathlib import Path
from queue import Queue

from PySide2.QtCore import Signal, Slot
from PySide2.QtWidgets import QAction, QMenu

from modules.gui.ui_resource import IconRsc
from modules.gui.widgets.excel_dialog import ExcelImportDialog
from modules.gui.widgets.file_dialog import FileDialog
from modules.itemview.excel_read import KnechtExcelDataThread
from modules.itemview.item import KnechtItem
from modules.itemview.model import KnechtModel
from modules.itemview.xml import SaveLoadController
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class ImportMenu(QMenu):
    new_model_ready = Signal(KnechtModel, Path)
    excel_data_thread_signal = Signal(tuple)

    def __init__(self, ui):
        """ Menu to import data

        :param modules.gui.main_ui.KnechtWindow ui:
        """
        super(ImportMenu, self).__init__(_("Import"), ui)
        self.ui = ui

        xl_action = QAction(IconRsc.get_icon('excel'), _('V-Plus Browser'), self)
        xl_action.triggered.connect(self.open_xlsx)

        self.addAction(xl_action)

    @Slot()
    def open_xlsx(self, file: Path=None, pos_file: Path=None):
        if not file:
            file = FileDialog.open(self.ui, None, 'xlsx')

        if not file:
            LOGGER.info('Open Xlsx File dialog canceled.')
            return

        xl_dialog = ExcelImportDialog(self.ui, Path(file), pos_file)
        xl_dialog.destroyed.connect(self._report_destroyed)
        xl_dialog.finished.connect(self.xlsx_result)
        xl_dialog.open()

        LOGGER.debug('Xlsx file dialog opened')

    @Slot(ExcelImportDialog)
    def xlsx_result(self, xl: ExcelImportDialog):
        options = (xl.check_read_trim.isChecked(),
                   xl.check_read_options.isChecked(),
                   xl.check_read_packages.isChecked(),
                   xl.check_pr_fam_filter_packages.isChecked(),
                   xl.read_fakom,
                   )

        # Start ExcelData to KnechtModel conversion thread
        queue = Queue()
        xl_thread = KnechtExcelDataThread(Path(xl.file.as_posix()), queue)
        xl_thread.finished.connect(self.xlsx_conversion_finished)
        xl_thread.error.connect(self.ui.msg)
        xl_thread.progress_msg.connect(self.xlsx_progress_msg)
        xl_thread.start()
        queue.put(
            (xl.data, xl.selected_models, xl.selected_pr_families, *options)
            )
        xl.deleteLater()

    @Slot(str)
    def xlsx_progress_msg(self, msg: str):
        view = self.ui.view_mgr.current_view()
        view.progress_msg.msg(msg)
        view.progress_msg.show_progress()

        if not msg:
            view.progress_msg.hide_progress()

    @Slot(Path, KnechtItem)
    def xlsx_conversion_finished(self, file: Path, root_item: KnechtItem):
        # Move item to main thread
        _root_item = SaveLoadController.copy_item_to_main_thread(root_item)

        # Emit new model
        new_model = KnechtModel(_root_item)
        self.new_model_ready.emit(new_model, file.with_suffix('.xml'))

    @staticmethod
    def _report_destroyed(widget):
        LOGGER.info('Dialog destroyed: %s', type(widget))
