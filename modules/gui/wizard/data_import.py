from pathlib import Path

from PySide2.QtCore import Slot
from PySide2.QtWidgets import QWizardPage

from modules.globals import Resource
from modules.gui.gui_utils import SetupWidget
from modules.gui.ui_generic_tab import GenericTabWidget
from modules.gui.ui_resource import IconRsc
from modules.gui.widgets.excel_dialog import ExcelImportDialog
from modules.gui.widgets.fakom_dialog import FakomImportDialog
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class ImportWizardPage(QWizardPage):
    no_data = _('Keine Daten vorhanden.')
    page_title = _('Daten Import')

    def __init__(self, wizard):
        """ Wizard Page to import data

        :param modules.gui.wizard.wizard.PresetWizard wizard: The parent wizard
        """
        super(ImportWizardPage, self).__init__()
        self.wizard = wizard
        SetupWidget.from_ui_file(self, Resource.ui_paths['wizard_import'])

        self.setTitle(self.page_title)
        self.setSubTitle(_('Für die Preseterstellung werden Farb- sowie Trimlinedaten benötigt. '
                           'Im Anschluss an den Importvorgang kann dieser Dialog fortgesetzt werden.'))

        # -- Setup Page Ui ---
        self.box_data.setTitle(_('Import'))
        self.btn_fakom.setText(_('FaKom Import starten'))
        self.btn_fakom.setIcon(IconRsc.get_icon('fakom'))
        self.result_box.setTitle(_('Ergebnis'))

        self.btn_fakom.released.connect(self.import_fakom)
        self.data = None

    def initializePage(self):
        self.update_result()

    @Slot()
    def import_fakom(self):
        fakom_dlg = FakomImportDialog(self.wizard.ui)
        fakom_dlg.open_fakom_xlsx.connect(self.start_xl_dialog)
        GenericTabWidget(self.wizard.ui, fakom_dlg, name=_('Assistent FaKom Import'))

    @Slot(Path, Path)
    def start_xl_dialog(self, file: Path, pos_file: Path):
        xl_dialog = ExcelImportDialog(self.wizard.ui, file, pos_file, fixed_options=True)
        xl_dialog.finished.connect(self.xl_result)
        GenericTabWidget(self.wizard.ui, xl_dialog, name=_('Assistent V Plus Import'))

    @Slot(ExcelImportDialog)
    def xl_result(self, xl: ExcelImportDialog):
        self.wizard.session.data.import_data = xl.data
        self.completeChanged.emit()
        xl.deleteLater()

    def update_result(self):
        data = self.wizard.session.data.import_data

        if not data.models:
            self.result_label.setText(self.no_data)
            self.result_icn.setPixmap(IconRsc.get_pixmap('check_box_empty'))
            return

        t = _('Daten geladen. {}[{}] Modelle; {}[{}] PR-Familien').format(
            len(data.selected_models), len(data.models),
            len(data.selected_pr_families), len(data.pr_families)
            )
        self.result_label.setText(t)
        self.result_icn.setPixmap(IconRsc.get_pixmap('check_box'))

    def validatePage(self):
        return self.wizard.save_last_session()

    def isComplete(self):
        self.update_result()

        if not self.wizard.session.data.import_data.models:
            return False

        return True
