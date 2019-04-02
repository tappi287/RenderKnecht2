from PySide2.QtCore import Slot
from PySide2.QtWidgets import QWizard

from modules.gui.widgets.message_box import AskToContinue
from modules.gui.wizard.data_import import ImportWizardPage
from modules.gui.wizard.fakom import FakomWizardPage
from modules.gui.wizard.session import WizardSession
from modules.gui.wizard.start import WelcomeWizardPage
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
        self.session = WizardSession()

        self.page_welcome = WelcomeWizardPage(self)
        self.page_import = ImportWizardPage(self)
        self.page_fakom = FakomWizardPage(self)
        self.addPage(self.page_welcome)
        self.addPage(self.page_import)
        self.addPage(self.page_fakom)

    @Slot()
    def restore_last_session(self):
        self.session.load(self.session.last_session_file)
        self.session_loaded()

    def save_last_session(self) -> bool:
        """ Session auto save """
        self.ui.msg(_('Wizard Session wird automatisch gespeichert.'))
        return self.session.save()

    def session_loaded(self):
        """ Inform Wizard pages of new session data """
        self.page_welcome.reload_pkg_filter()
        self.page_import.completeChanged.emit()

        self.ui.msg(_('Wizard Session geladen.'))

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
