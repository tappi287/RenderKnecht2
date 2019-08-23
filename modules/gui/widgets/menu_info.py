from PySide2.QtCore import QObject, QTimer, Slot
from PySide2.QtWidgets import QMenu

from modules.gui.ui_generic_tab import GenericTabWidget
from modules.gui.ui_resource import IconRsc
from modules.gui.widgets.about_page import KnechtAbout
from modules.gui.widgets.help_page import KnechtHelpPage
from modules.gui.widgets.welcome_page import KnechtWelcome
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class InfoMenu(QObject):
    def __init__(self, ui, menu: QMenu=None):
        """ The Info menu

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
        self.ui.actionInfo.triggered.connect(self.show_info_page)
        self.ui.actionInfo.setEnabled(True)
        self.ui.actionWelcome.triggered.connect(self.show_welcome_page)
        self.ui.actionWelcome.setEnabled(True)
        self.ui.actionHelp.triggered.connect(self.show_docs)
        self.ui.actionHelp.setEnabled(True)

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

    def show_info_page(self):
        # --- About Page ---
        about_page = KnechtAbout(self.ui)

        # Skip if view already exists
        if self.ui.view_mgr.get_view_by_name(about_page.windowTitle()):
            del about_page
            return

        GenericTabWidget(self.ui, about_page)

    def show_welcome_page(self):
        # --- Welcome Page ---
        welcome_page = KnechtWelcome(self.ui)

        # Skip if view already exists
        if self.ui.view_mgr.get_view_by_name(welcome_page.windowTitle()):
            del welcome_page
            return

        GenericTabWidget(self.ui, welcome_page)

    def show_docs(self):
        # --- Help Page ---
        docs_page = KnechtHelpPage(self.ui)

        # Skip if view already exists
        if self.ui.view_mgr.get_view_by_name(docs_page.windowTitle()):
            del docs_page
            return

        GenericTabWidget(self.ui, docs_page)
