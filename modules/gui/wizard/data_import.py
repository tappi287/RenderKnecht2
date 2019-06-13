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
    fakom_import_txt = _('FaKom Import starten')
    fakom_restart_txt = _('Daten vorhanden - FaKom Import neustarten')

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
        self.btn_fakom.setText(self.fakom_import_txt)
        self.btn_fakom.setIcon(IconRsc.get_icon('fakom'))
        self.btn_reset_fakom.setIcon(IconRsc.get_icon('reset'))
        self.btn_reset_fakom.hide()
        self.btn_reset_fakom.released.connect(self.wizard.restart_session)
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
        self.wizard.session.reset_session()
        self.wizard.session.data.import_data = xl.data

        self.completeChanged.emit()
        xl.deleteLater()

    def update_result(self):
        data = self.wizard.session.data.import_data
        result = True

        if not data.models:
            result = False

        if not len(data.selected_models) or not len(data.selected_pr_families):
            if result:
                self.wizard.ui.msg(_('Keine Modelle oder PR-Familien in den Import Daten ausgewählt. '
                                 'Bitte beim Import mindestens ein Modell und eine PR-Familie wählen.'), 12000)
                result = False

        if not result:
            self.result_label.setText(self.no_data)
            self.result_icn.setPixmap(IconRsc.get_pixmap('check_box_empty'))
            self.btn_reset_fakom.hide()
            self.btn_fakom.setEnabled(True)
            self.btn_fakom.setText(self.fakom_import_txt)
            return result

        self.btn_reset_fakom.show()
        t = _('Daten geladen. {}[{}] Modelle; {}[{}] PR-Familien').format(
            len(data.selected_models), len(data.models),
            len(data.selected_pr_families), len(data.pr_families)
            )
        self.btn_fakom.setEnabled(False)
        self.btn_fakom.setText(self.fakom_restart_txt)
        self.result_label.setText(t)
        self.result_icn.setPixmap(IconRsc.get_pixmap('check_box'))
        return result

    def validatePage(self):
        # Update Package filter
        self.wizard.session.data.update_pkg_filter(self.wizard.page_welcome.read_pkg_filter())
        # Save Session
        return self.wizard.save_last_session()

    def isComplete(self):
        if not self.update_result():
            return False

        return True
