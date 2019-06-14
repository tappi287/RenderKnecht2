from PySide2.QtCore import QObject, QTimer, Slot
from PySide2.QtWidgets import QMenu

from modules.gui.ui_resource import IconRsc
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class InfoMenu(QObject):
    def __init__(self, ui, menu: QMenu=None):
        """ The File menu

        :param modules.gui.main_ui.KnechtWindow ui:
        :param menu: Menu already setup in ui file
        """
        super(InfoMenu, self).__init__(parent=ui)
        self.ui = ui
        self.menu: QMenu = menu

        for action in self.menu.actions():
            action.setEnabled(False)

        self.ui.actionVersionCheck.triggered.connect(self.update_check)
        self.ui.actionVersionCheck.setEnabled(True)

        QTimer.singleShot(1, self.delayed_setup)

    def update_ready(self):
        update_icon = IconRsc.get_icon('update-ready')
        self.menu.setIcon(update_icon)
        self.ui.actionVersionCheck.setIcon(update_icon)

    def delayed_setup(self):
        self.ui.updater.update_available.connect(self.set_update_menu_entry)

    def update_check(self):
        self.ui.check_for_updates()

    @Slot(str)
    def set_update_menu_entry(self, version_text):
        self.ui.actionVersionCheck.setText(
            _('Aktualisierung auf Version {}...').format(version_text)
            )
