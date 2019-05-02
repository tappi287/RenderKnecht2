from PySide2.QtCore import Slot
from PySide2.QtWidgets import QWizard, QWizardPage

from modules.gui.widgets.message_box import AskToContinue
from modules.gui.wizard.data_import import ImportWizardPage
from modules.gui.wizard.fakom import FakomWizardPage
from modules.gui.wizard.preset import PresetWizardPage
from modules.gui.wizard.session import WizardSession
from modules.gui.wizard.start import WelcomeWizardPage
from modules.itemview.model import KnechtModel
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class PresetWizard(QWizard):
    title = _('Preset Wizard')

    def __init__(self, ui):
        """ Wizard assisting the user to create presets from Vplus + FaKom data

        :param modules.gui.main_ui.KnechtWindow ui: Main Window
        """
        super(PresetWizard, self).__init__(ui)
        self.ui = ui
        self.setWindowTitle(self.title)
        self.setWizardStyle(QWizard.ModernStyle)

        self._asked_for_close = False
        self.preset_page_ids = set()
        self.session = WizardSession()

        self.setButtonText(QWizard.BackButton, _('Zurück'))
        self.setButtonText(QWizard.NextButton, _('Weiter'))
        self.setButtonText(QWizard.FinishButton, _('Abschließen'))
        self.setButtonText(QWizard.CancelButton, _('Abbrechen'))

        self.page_welcome = WelcomeWizardPage(self)
        self.page_import = ImportWizardPage(self)
        self.page_fakom = FakomWizardPage(self)
        self.page_placeholder = PlaceholderPage(self)
        self.addPage(self.page_welcome)
        self.addPage(self.page_import)
        self.addPage(self.page_fakom)
        self.addPage(self.page_placeholder)

    @Slot()
    def restore_last_session(self):
        self.session.load(self.session.last_session_file)
        self.session_loaded()

    def save_last_session(self) -> bool:
        """ Session auto save """
        self.ui.msg(_('Wizard Session wurde automatisch gespeichert.'))
        return self.session.save()

    def session_loaded(self):
        """ Inform Wizard pages of new session data """
        self.page_welcome.reload_pkg_filter()
        self.page_import.completeChanged.emit()

        self.ui.msg(_('Wizard Session geladen.'))

    def create_preset_pages(self):
        for old_page_id in self.preset_page_ids:
            self.removePage(old_page_id)

        LOGGER.debug('Cleared %s preset pages.', len(self.preset_page_ids))
        self.preset_page_ids = set()

        for model, fakom_ls in self.session.data.fakom_selection.items():
            self.session.update_preset_page_models(model)
            # TODO: Populate page models with available pr options and packages

            for fakom in fakom_ls:
                preset_page = PresetWizardPage(self, model, fakom)
                page_id = self.addPage(preset_page)
                self.session.load_preset_page_options(page_id, model, preset_page)
                self.preset_page_ids.add(page_id)

        LOGGER.debug('Created %s preset pages.', len(self.preset_page_ids))

    def reject(self):
        self.close()

    def accept(self):
        self._asked_for_close = True
        self.close()

    def _ask_close(self):
        if self._asked_for_close:
            return False

        msg_box = AskToContinue(self)

        if not msg_box.ask(
            title=self.title,
            txt=_('Soll der Assistent wirklich abgebrochen werden?'),
            ok_btn_txt=_('Ja'),
            abort_btn_txt=_('Nein'),
                ):
            # Cancel close
            return True

        return False

    def closeEvent(self, close_event):
        if self._ask_close():
            close_event.ignore()
            return False

        LOGGER.info('Preset Wizard closed.')
        close_event.accept()


class PlaceholderPage(QWizardPage):
    def __init__(self, wizard):
        """ We put a placeholder page in front of pages we need to dynamically create
            and do not want the finish button to appear yet. It will be automatically skipped.
            Also acts as a session save point.
        """
        super(PlaceholderPage, self).__init__()
        self.wizard = wizard
        self.wizard.currentIdChanged.connect(self.current_page_changed)
        self.id: int = -1
        self.previous_page_id: int = -1

    def initializePage(self, *args, **kwargs):
        self.id = self.wizard.currentId()
        self.wizard.save_last_session()

    def cleanupPage(self, *args, **kwargs):
        self.wizard.save_last_session()

    def current_page_changed(self, page_id: int):
        """ Skip page visits automatically forward or backward """
        if page_id == self.id:
            if self.id > self.previous_page_id:
                self.wizard.next()
            else:
                self.wizard.back()
            LOGGER.debug('Skipping placeholder page %s Previous page: %s', self.id, self.previous_page_id)
        else:
            self.previous_page_id = page_id
