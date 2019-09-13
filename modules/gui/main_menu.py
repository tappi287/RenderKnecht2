from PySide2 import QtCore

from modules.gui.widgets.menu_create import CreateMenu
from modules.gui.widgets.menu_deltagen import DeltaGenMenu
from modules.gui.widgets.menu_edit import EditMenu
from modules.gui.widgets.menu_file import FileMenu
from modules.gui.widgets.menu_info import InfoMenu
from modules.gui.widgets.menu_tab_context import TabContextMenu
from modules.gui.widgets.menu_tree import TreeMenu
from modules.gui.widgets.menu_view import ViewMenu
from modules.gui.widgets.menu_language import LanguageMenu
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class MainWindowMenu(QtCore.QObject):
    def __init__(self, ui):
        super(MainWindowMenu, self).__init__(parent=ui)
        self.ui = ui

        # File menu already added through UI definition file
        self.file_menu = FileMenu(ui)

        self.edit_menu = EditMenu(ui)

        self.tree_menu = TreeMenu(parent_widget=ui, ui=ui)

        self.create_menu = CreateMenu(ui)

        self.view_menu = ViewMenu(ui)

        self.dg_menu = DeltaGenMenu(ui)

        self.lang_menu = LanguageMenu(ui)

        self.info_menu = InfoMenu(ui, ui.menuInfo)

        # Document tab context menu
        self.tab_context = TabContextMenu(self.ui)

        # Clear menuBar and add in order
        self.ui.menuBar().clear()
        for menu in [self.file_menu.menu, self.edit_menu, self.tree_menu, self.create_menu,
                     self.view_menu, self.dg_menu, self.lang_menu, self.info_menu.menu]:
            self.ui.menuBar().addMenu(menu)
