from pathlib import Path

from PySide2.QtCore import QEvent, QUrl, Qt
from PySide2.QtGui import QDesktopServices
from PySide2.QtWidgets import QAction, QActionGroup, QMenu

from modules.gui.ui_resource import IconRsc
from modules.gui.widgets.path_util import path_exists
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class TabContextMenu(QMenu):
    def __init__(self, ui, menu_name: str = _('Baum Kontextmenü')):
        """ Context menu of document tabs

        :param modules.gui.main_ui.KnechtWindow ui: main window ui class
        :param str menu_name: name of the menu
        """
        super(TabContextMenu, self).__init__(menu_name, ui)
        self.ui, self.status_bar = ui, ui.statusBar()

        self.context_tab_index = -1

        grp = QActionGroup(self)
        self.copy_action = QAction(IconRsc.get_icon('options'), _('Dokumenten Pfad in Zwischenablage kopieren'), grp)
        self.open_action = QAction(IconRsc.get_icon('folder'), _('Dokumenten Pfad öffnen'), grp)
        grp.triggered.connect(self.doc_action)
        self.addActions([self.copy_action, self.open_action])

        self.tab_bar = self.ui.srcTabWidget.tabBar()
        self.tab_bar.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.ContextMenu:
            # Hold Control and Shift to display dev context
            if event.modifiers() == Qt.ShiftModifier | Qt.ControlModifier:
                pass
            self.context_tab_index = self.tab_bar.tabAt(self.tab_bar.mapFromGlobal(event.globalPos()))
            LOGGER.debug('Context at tab: %s', self.context_tab_index)

            self.popup(event.globalPos())
            return True

        return False

    def doc_action(self, action: QAction):
        file, tab_page = Path('.'), None

        if self.context_tab_index >= 0:
            tab_page = self.ui.view_mgr.tab.widget(self.context_tab_index)
            file = self.ui.view_mgr.file_mgr.get_file_from_widget(tab_page) or Path('.')

        if not path_exists(file) or not file.is_file():
            self.ui.msg(
                _('Kein gültiger Pfad für das Dokument gesetzt. Das Dokument muss zuerst gespeichert werden.'), 5000)
            return

        if action == self.copy_action:
            self.ui.app.clipboard().setText(file.as_posix())
            self.ui.msg(_('Dokumenten Pfad wurde in die Zwischenablage kopiert.<br/><i>{}<i>').format(file.as_posix()))
        elif action == self.open_action:
            q = QUrl.fromLocalFile(file.parent.as_posix())
            QDesktopServices.openUrl(q)
