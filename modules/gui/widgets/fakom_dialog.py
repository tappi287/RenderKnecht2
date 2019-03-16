from pathlib import Path

from PySide2.QtCore import Signal, Slot
from PySide2.QtWidgets import QDialog

from modules import KnechtSettings
from modules.globals import Resource
from modules.gui.gui_utils import SetupWidget
from modules.gui.widgets.path_util import SetDirectoryPath
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class FakomImportDialog(QDialog):
    open_fakom_xlsx = Signal(Path, Path)

    def __init__(self, ui):
        """ Dialog to choose files for Fakom + V Plus import

        :param modules.gui.main_ui.KnechtWindow ui: Main Window
        """
        super(FakomImportDialog, self).__init__(ui)
        SetupWidget.from_ui_file(self, Resource.ui_paths['knecht_fakom'])

        # --- Attributes ---
        self.ui = ui

        # --- POS path UI ---
        self.pos_path = SetDirectoryPath(
            self.ui, mode='file',
            line_edit=self.lineEdit_fakom,
            tool_button=self.toolBtn_fakom,
            dialog_args=(_('POS Varianten Xml auswählen ...'), _('DeltaGen POS Datei (*.xml;*.pos);'),),
            reject_invalid_path_edits=True,
            )
        self.pos_path.set_path(KnechtSettings.fakom.get('last_pos_file'))
        self.pos_path.path_changed.connect(self.pos_path_changed)

        # --- V plus path UI ---
        self.xlsx_path = SetDirectoryPath(
            self.ui, mode='file',
            line_edit=self.lineEdit_vplus,
            tool_button=self.toolBtn_vplus,
            dialog_args=(_('Excel Dateien *.xlsx auswaehlen'), _('Excel Dateien (*.xlsx);')),
            reject_invalid_path_edits=True,
            )
        self.xlsx_path.set_path(KnechtSettings.fakom.get('last_xlsx_file'))
        self.xlsx_path.path_changed.connect(self.xlsx_path_changed)

    @Slot(Path)
    def pos_path_changed(self, pos_file: Path):
        KnechtSettings.fakom['last_pos_file'] = pos_file.as_posix()

    @Slot(Path)
    def xlsx_path_changed(self, xlsx_file: Path):
        KnechtSettings.fakom['last_xlsx_file'] = xlsx_file.as_posix()

    def verify_paths(self):
        for p in (self.pos_path.path, self.xlsx_path.path):
            if p is None or not p.exists() or not p.is_file():
                break
        else:
            return True

        return False

    def reject(self):
        self.close()

    def accept(self):
        if self.verify_paths():
            self.open_fakom_xlsx.emit(self.xlsx_path.path, self.pos_path.path)

        self.close()

    def closeEvent(self, close_event):
        self._finalize_dialog()
        close_event.accept()

    def _finalize_dialog(self, self_destruct: bool=True):
        if self_destruct:
            self.deleteLater()
