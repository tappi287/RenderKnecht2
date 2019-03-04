from pathlib import Path

from PySide2.QtCore import Slot, Signal
from PySide2.QtWidgets import QAction, QMenu

from modules.gui.ui_resource import IconRsc
from modules.gui.widgets.excel_dialog import ExcelImportDialog
from modules.gui.widgets.file_dialog import FileDialog
from modules.itemview.excel_read import KnechtExcelDataToModel
from modules.itemview.model import KnechtModel
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class ImportMenu(QMenu):
    new_model_ready = Signal(KnechtModel, Path)

    def __init__(self, ui):
        super(ImportMenu, self).__init__(_("Import"), ui)
        self.ui = ui

        xl_action = QAction(IconRsc.get_icon('excel'), _('V-Plus Browser'), self)
        xl_action.triggered.connect(self.open_xlsx)
        self.addAction(xl_action)

    def open_xlsx(self, file: Path=None):
        if not file:
            file = FileDialog.open(self.ui, None, 'xlsx')

        if not file:
            LOGGER.info('Open Xlsx File dialog canceled.')
            return

        xl_dialog = ExcelImportDialog(self.ui, Path(file))
        xl_dialog.destroyed.connect(self._report_destroyed)
        xl_dialog.finished.connect(self.xlsx_result)
        xl_dialog.open()
        LOGGER.debug('Xlsx file dialog opened')

    @Slot(ExcelImportDialog)
    def xlsx_result(self, xl: ExcelImportDialog):
        options = (xl.check_read_trim.isChecked(),
                   xl.check_read_options.isChecked(),
                   xl.check_read_packages.isChecked())

        xl_reader = KnechtExcelDataToModel(
            xl.data, xl.selected_models, xl.selected_pr_families, *options
            )
        new_model = xl_reader.create_model()
        if new_model.rowCount():
            self.new_model_ready.emit(new_model, xl.file.with_suffix('.xml'))
        LOGGER.debug('New Model created from ExcelData: %s', new_model.rowCount())

        xl.deleteLater()

    @staticmethod
    def _report_destroyed(widget):
        LOGGER.info('Dialog destroyed: %s', type(widget))
