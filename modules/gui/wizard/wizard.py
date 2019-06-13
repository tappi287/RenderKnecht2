from pathlib import Path
from typing import Union

from PySide2.QtCore import Slot
from PySide2.QtWidgets import QWizard, QWizardPage, QPushButton

from modules import KnechtSettings
from modules.gui.clipboard import TreeClipboard
from modules.gui.ui_resource import IconRsc
from modules.gui.widgets.file_dialog import FileDialog
from modules.gui.widgets.message_box import AskToContinue
from modules.gui.wizard.data_import import ImportWizardPage
from modules.gui.wizard.fakom import FakomWizardPage
from modules.gui.wizard.menus import WizardSessionMenu, WizardNavMenu
from modules.gui.wizard.result import ResultWizardPage
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

    def __init__(self, ui, file: Union[Path, str]=None):
        """ Wizard assisting the user to create presets from Vplus + FaKom data

        :param modules.gui.main_ui.KnechtWindow ui: Main Window
        """
        super(PresetWizard, self).__init__(parent=ui)
        self.ui = ui
        self.setWindowTitle(self.title)
        self.setWizardStyle(QWizard.ModernStyle)

        self._asked_for_close = False
        self.session = WizardSession(self)

        self.setButtonText(QWizard.BackButton, _('Zurück'))
        self.setButtonText(QWizard.NextButton, _('Weiter'))
        self.setButtonText(QWizard.FinishButton, _('Abschließen'))
        self.setButtonText(QWizard.CancelButton, _('Abbrechen'))

        self.automagic_clipboard = TreeClipboard()

        # --- Session Management ---
        session_btn = QPushButton(self)
        session_btn.setMinimumWidth(150)
        session_btn.setText(_('Sitzung'))
        session_btn.setMenu(WizardSessionMenu(self))
        self.setButton(self.CustomButton1, session_btn)
        self.setOption(self.HaveCustomButton1, True)

        # --- Navigation Menu ---
        nav_btn = QPushButton(self)
        nav_btn.setMinimumWidth(150)
        self.nav_menu = WizardNavMenu(self, nav_btn)
        self.setButton(self.CustomButton2, nav_btn)
        self.setOption(self.HaveCustomButton2, True)

        self.page_welcome = WelcomeWizardPage(self)
        self.page_import = ImportWizardPage(self)
        self.page_fakom = FakomWizardPage(self)
        self.page_placeholder = PlaceholderPage(self)
        self.page_result = ResultWizardPage(self)
        self.addPage(self.page_welcome)
        self.addPage(self.page_import)
        self.addPage(self.page_fakom)
        self.addPage(self.page_placeholder)

        # Load session file if provided
        if file and Path(file).exists():
            self.open_session_file(Path(file).as_posix())

    @Slot()
    def restore_last_session(self):
        if not self.restart_session():
            return

        if self.session.load(self.session.last_session_file):
            self.session_loaded()
        else:
            self.ui.msg(_('Wizard Session konnte nicht geladen werden!'))

    @Slot()
    def open_session_file(self, file: str=None):
        if not file:
            file = FileDialog.open(self.ui, None, 'rksession')

        if not file:
            # File dialog canceled
            return

        if not self.restart_session():
            return

        result = self.session.load(Path(file))

        if result:
            self.ui.msg(_('Wizard Session geladen.'))
        else:
            self.ui.msg(_('Fehler beim Laden der Wizard Session Datei.'))

    @Slot()
    def save_session_file(self, file: str=None):
        if not file:
            file, file_type = FileDialog.save(self.ui, Path(KnechtSettings.app['current_path']), 'rksession')

        if not file:
            # File dialog canceled
            return

        result = self.session.save(Path(file))

        if result:
            self.ui.msg(_('Wizard Session gespeichert.'))
            # Add recent file entry
            KnechtSettings.add_recent_file(file, 'rksession')
        else:
            self.ui.msg(_('Fehler beim Speichern der Wizard Session.'))

    def save_last_session(self) -> bool:
        """ Session auto save """
        result = self.session.save()
        if result:
            self.ui.msg(_('Wizard Session wurde automatisch gespeichert.'))
        else:
            self.ui.msg(_('Fehler! Wizard Session konnte nicht gespeichert werden.'))

        return result

    def session_loaded(self):
        """ Inform Wizard pages of new session data """
        self.page_welcome.reload_pkg_filter()
        self.page_import.completeChanged.emit()

        self.ui.msg(_('Wizard Session geladen.'))

    def create_document(self):
        new_file = Path('Preset_Wizard_Doc.xml')

        try:
            src_model = self.page_result.result_tree.model().sourceModel()
            if not src_model.root_item.childCount():
                return
        except Exception as e:
            LOGGER.error('Preset Wizard could not create document: %s', e)
            return

        LOGGER.debug('Creating Preset Wizard Document')
        self.ui.view_mgr.create_view(
            src_model, new_file
            )

    def restart_session(self) -> bool:
        if not self.ask_restart():
            return False

        while self.currentId() != self.startId() and self.currentId() != -1:
            self.back()

        self.session.reset_session()
        return True

    def reject(self):
        self.close()

    def accept(self):
        self.create_document()
        self._asked_for_close = True
        self.close()

    def ask_restart(self):
        if not self.currentId() > self.startId():
            # Already on start page
            return True

        msg_box = AskToContinue(self)

        if not msg_box.ask(
            title=self.title,
            txt=_('Soll der Assistent neu gestartet werden? Die vorhandenen Sessiondaten gehen verloren.'),
            ok_btn_txt=_('Ok'),
            abort_btn_txt=_('Abbrechen'),
                ):
            # Do not restart
            return False

        # User Confirmed restart
        return True

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
        self.wizard.nav_menu.button.setEnabled(False)

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
