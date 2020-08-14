from pathlib import Path

from PySide2.QtCore import Signal, Slot
from PySide2.QtWidgets import QDialog, QGroupBox, QLabel, QLineEdit, QToolButton

from modules import KnechtSettings
from modules.globals import Resource
from modules.gui.gui_utils import SetupWidget
from modules.gui.widgets.path_util import SetDirectoryPath, path_exists
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
        super(FakomImportDialog, self).__init__()
        SetupWidget.from_ui_file(self, Resource.ui_paths['knecht_fakom'])

        # --- Attributes ---
        self.ui = ui

        # CleanUp on application exit
        self.ui.app.aboutToQuit.connect(self.close)

        # --- Translations ---
        path_txt = _('Pfad:')
        path_status_tip = _('Pfad als Text in das Feld kopieren oder über den Dateidialog wählen.')
        path_btn_tip = _('Dateidialog öffnen um Datei oder Verzeichnis auszuwählen.')
        self.groupBox_fakom: QGroupBox
        self.groupBox_fakom.setTitle(_('POS Xml Varianten'))
        self.label_fakomDesc: QLabel
        self.label_fakomDesc.setText(_('DeltaGen POS XML Datei eines Freigabemodells auswählen. '
                                       'Die Farbschlüssel und Sitzbezug Kombinatorik wird aus den Action '
                                       'Listen der Xml Struktur gelutscht.'))
        self.label_fakomPath: QLabel
        self.label_fakomPath.setText(path_txt)
        self.lineEdit_fakom: QLineEdit
        self.lineEdit_fakom.setPlaceholderText(_('POS Xml Variantendatei auswählen...'))
        self.lineEdit_fakom.setStatusTip(path_status_tip)
        self.toolBtn_fakom: QToolButton
        self.toolBtn_fakom.setStatusTip(path_btn_tip)

        self.groupBox_vplus: QGroupBox
        self.groupBox_vplus.setTitle(_('V Plus Browserauszug'))
        self.label_vplus_desc: QLabel
        self.label_vplus_desc.setText(_('Pfad zum V Plus Browserauszug festlegen. Die verfügbaren '
                                        'Sitzbezüge(SIB), Vordersitze(VOS) und Lederumfänge(LUM) je Trimline '
                                        'werden ausgelesen.<br/><br/>Im nächsten Schritt können und sollten '
                                        '<b>Modelfilter</b> gesetzt werden.'))
        self.label_vplusPath: QLabel
        self.label_vplusPath.setText(path_txt)
        self.lineEdit_vplus: QLineEdit
        self.lineEdit_vplus.setPlaceholderText(_('V Plus Browserauszug auswählen...'))
        self.lineEdit_vplus.setStatusTip(path_status_tip)
        self.toolBtn_vplus: QToolButton
        self.toolBtn_vplus.setStatusTip(path_btn_tip)

        self.groupBox_info: QGroupBox
        self.groupBox_info.setTitle(_('Information zu Farbkombinationen'))
        self.label_info: QLabel
        self.label_info.setText(_('<span style=" font-weight:600; color:#aa0000;">ACHTUNG:</span> '
                                  'Die Farb- und Sitzbezugskombinationen werden aus den POS Varianten '
                                  'gelutscht und anschließend mit dem V Plus Browserauszug auf Sitzbezüge, '
                                  'Vordersitze und Lederumfänge abgeglichen. Sitzbezüge die im V Plus Dokument '
                                  'vorhanden sind, nicht aber in den POS Varianten, können nicht berücksichtigt '
                                  'werden.<br/><br/>Dieser Import garantiert keine Vollständigkeit oder Richtigkeit '
                                  'gegenüber der aktuellen FaKom. Er basiert ausschließlich auf der Datengrundlage der '
                                  'POS Varianten des DeltaGen Modells.'))

        # --- POS path UI ---
        self.pos_path = SetDirectoryPath(
            self, mode='file',
            line_edit=self.lineEdit_fakom,
            tool_button=self.toolBtn_fakom,
            dialog_args=(_('POS Varianten Xml auswählen ...'), _('DeltaGen POS Datei (*.xml;*.pos);'),),
            reject_invalid_path_edits=True,
            )
        self.pos_path.set_path(KnechtSettings.fakom.get('last_pos_file'))
        self.pos_path.path_changed.connect(self.pos_path_changed)

        # --- V plus path UI ---
        self.xlsx_path = SetDirectoryPath(
            self, mode='file',
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
            if p is None or not path_exists(p) or not p.is_file():
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
            pass
            # self.deleteLater()
