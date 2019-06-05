from PySide2.QtCore import QObject
from PySide2.QtWidgets import QAction, QMenu

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

        save = QAction(IconRsc.get_icon('disk'), _('Speichern unter ...'), self)
        load = QAction(IconRsc.get_icon('folder'), _('Session oeffnen ...'), self)
        restore = QAction(IconRsc.get_icon('undo'), _('Letzte Sitzung wiederherstellen'), self)
        reset = QAction(IconRsc.get_icon('reset'), _('Session neustarten'), self)

        load.setStatusTip(_('Wizard Session aus Datei laden'))
        save.setStatusTip(_('Wizard Session in Datei sichern'))
        restore.setStatusTip(_('Letzte automatisch gesicherte Session wiederherstellen'))
        reset.setStatusTip(_('Preset Wizard neustarten und vorhandene Daten verwerfen'))

        load.triggered.connect(self._load_session)
        save.triggered.connect(self._save_session)
        restore.triggered.connect(self._restore_session)
        reset.triggered.connect(self._reset_session)

        self.addActions((save, load, restore, reset))

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
