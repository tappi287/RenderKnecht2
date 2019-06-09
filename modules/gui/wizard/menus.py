from PySide2.QtCore import QObject
from PySide2.QtWidgets import QAction, QMenu, QPushButton

from modules.gui.ui_resource import IconRsc
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class WizardSessionMenu(QMenu):

    def __init__(self, wizard):
        """ Preset Wizard Session Management Menu

        :param modules.gui.wizard.PresetWizard wizard:
        """
        super(WizardSessionMenu, self).__init__(parent=wizard.ui)
        self.wizard = wizard
        self.ui = wizard.ui

        load = QAction(IconRsc.get_icon('folder'), _('Öffnen'), self)
        save = QAction(IconRsc.get_icon('disk'), _('Speichern unter ...'), self)
        restore = QAction(IconRsc.get_icon('undo'), _('Letzte Sitzung wiederherstellen'), self)
        reset = QAction(IconRsc.get_icon('reset'), _('Zurücksetzen'), self)

        load.setStatusTip(_('Wizard Sitzung aus Datei laden'))
        save.setStatusTip(_('Wizard Sitzung in Datei sichern'))
        restore.setStatusTip(_('Letzte automatisch gesicherte Sitzung wiederherstellen'))
        reset.setStatusTip(_('Preset Wizard neustarten und vorhandene Daten verwerfen'))

        load.triggered.connect(self._load_session)
        save.triggered.connect(self._save_session)
        restore.triggered.connect(self._restore_session)
        reset.triggered.connect(self._reset_session)

        self.addActions((load, save, restore, reset))

    def _load_session(self):
        self.wizard.open_session_file()

    def _save_session(self):
        self.wizard.save_session_file()

    def _restore_session(self):
        self.wizard.restore_last_session()

    def _reset_session(self):
        if not self.wizard.ask_restart():
            return

        self.wizard.restart_session()


class WizardNavMenu(QMenu):

    def __init__(self, wizard, menu_button: QPushButton):
        """ Preset Wizard Session Navigation Menu

        :param modules.gui.wizard.PresetWizard wizard:
        :param QPushButton menu_button: the button which displays the menu
        """
        super(WizardNavMenu, self).__init__(parent=wizard.ui)
        self.wizard = wizard
        self.button = menu_button
        self.button.setEnabled(False)
        self.button.setText(_('Navigation'))
        self.button.setMenu(self)

    def create_preset_page_entries(self):
        self.clear()
        num_pages = len(self.wizard.session.data.preset_page_ids)

        if not num_pages:
            empty_entry = QAction(IconRsc.get_icon('close'), _('Keine Einträge vorhanden'), self)
            empty_entry.setDisabled(True)
            self.button.setEnabled(False)
            return

        for page_id in self.wizard.session.data.preset_page_ids:
            current_num = page_id - 3
            page = self.wizard.page(page_id)
            title = f'{current_num:02d}/{num_pages:02d} - {page.model} {page.fakom}'

            entry = QAction(IconRsc.get_icon('preset'), title, self)
            entry.target_id = page_id
            entry.triggered.connect(self.navigate_to_page)
            self.addAction(entry)

        self.button.setEnabled(True)

    def navigate_to_page(self):
        menu_entry = self.sender()
        if not menu_entry.target_id:
            return

        while self.wizard.currentId() != menu_entry.target_id:
            if self.wizard.currentId() < menu_entry.target_id:
                self.wizard.next()
            elif self.wizard.currentId() > menu_entry.target_id:
                self.wizard.back()
            else:
                break
