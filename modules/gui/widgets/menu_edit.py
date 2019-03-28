from PySide2.QtWidgets import QMenu, QAction, QActionGroup
from PySide2.QtCore import Signal, QTimer, Slot
from PySide2.QtGui import QKeySequence

from modules.gui.ui_resource import IconRsc
from modules.gui.widgets.search_dialog import SearchDialog
from modules.log import init_logging
from modules.language import get_translation
from modules.gui.widgets.history import DocHistoryWidget

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class EditMenu(QMenu):

    enable_undo_actions = Signal(bool)

    def __init__(self, ui, menu_name: str = _('Bearbeiten')):
        """
        :param modules.gui.main_ui.KnechtWindow ui: The main ui class
        :param str menu_name: Edit Menu display name
        """
        super(EditMenu, self).__init__(menu_name, ui)
        self.ui = ui
        self.view = None

        # View Editor
        self.history = DocHistoryWidget(ui, self)

        self.undo_timer = QTimer()
        self.undo_timer.setInterval(50)
        self.undo_timer.setSingleShot(True)
        self.undo_timer.timeout.connect(self.undo_timeout_stop)

        self.undo_action_grp = QActionGroup(self)
        self.undo_action_grp.setExclusive(False)
        self.undo_action_grp.triggered.connect(self.undo_timeout_start)

        self.undo_action = ui.app.undo_grp.createUndoAction(self.undo_action_grp, prefix=_('Rückgängig:'))
        self.undo_action.setIcon(IconRsc.get_icon('undo'))
        self.undo_action.setShortcut(QKeySequence('Ctrl+Z'))
        self.addAction(self.undo_action)
        self.redo_action = ui.app.undo_grp.createRedoAction(self.undo_action_grp, prefix=_('Wiederherstellen:'))
        self.redo_action.setIcon(IconRsc.get_icon('redo'))
        self.redo_action.setShortcut(QKeySequence('Ctrl+Y'))
        self.addAction(self.redo_action)

        self.history_action = QAction(IconRsc.get_icon('later'), _('Historie\tStrg+H'), self)
        self.history_action.triggered.connect(self.toggle_history)
        self.history_action.setShortcut(QKeySequence('Ctrl+H'))
        self.addAction(self.history_action)

        self.addSeparator()

        self.search_action = QAction(IconRsc.get_icon('search'), _('Suchen und Ersetzen\tStrg+F'), self)
        self.search_action.triggered.connect(self.search)
        self.search_action.setShortcut(QKeySequence('Ctrl+F'))
        self.addAction(self.search_action)

        self.search_dlg = SearchDialog(self.ui)

        self.addSeparator()

        self.copy_action = QAction(IconRsc.get_icon('clip_copy'), _('Kopieren\tStrg+C'), self)
        self.copy_action.setShortcut(QKeySequence('Ctrl+C'))
        self.copy_action.triggered.connect(self.copy)
        self.addAction(self.copy_action)

        self.cut_action = QAction(IconRsc.get_icon('clip_cut'), _('Ausschneiden\tStrg+X'), self)
        self.cut_action.setShortcut(QKeySequence('Ctrl+X'))
        self.cut_action.triggered.connect(self.cut)
        self.addAction(self.cut_action)

        self.paste_action = QAction(IconRsc.get_icon('clip_paste'), _('Einfügen\tStrg+V'), self)
        self.paste_action.setShortcut(QKeySequence('Ctrl+V'))
        self.paste_action.triggered.connect(self.paste)
        self.addAction(self.paste_action)

        self.addSeparator()

        self.remove_rows_action = QAction(IconRsc.get_icon('trash-a'), _('Selektierte Zeilen entfernen\tEntf'), self)
        self.remove_rows_action.setShortcut(QKeySequence.Delete)
        self.remove_rows_action.triggered.connect(self.remove_rows)
        self.addAction(self.remove_rows_action)

        self.addSeparator()

        self.select_ref_action = QAction(_('Referenzen selektieren\tStrg+R'), self)
        self.select_ref_action.setShortcut(QKeySequence('Ctrl+R'))
        self.select_ref_action.triggered.connect(self.select_references)
        self.addAction(self.select_ref_action)

        self.select_none_action = QAction(_('Selektion aufheben\tStrg+D'), self)
        self.select_none_action.setShortcut(QKeySequence('Ctrl+D'))
        self.select_none_action.triggered.connect(self.deselect)
        self.addAction(self.select_none_action)

        self.aboutToShow.connect(self.update_view)

        QTimer.singleShot(1, self.delayed_setup)

    @Slot()
    def delayed_setup(self):
        """ Setup attributes that require a fully initialized ui"""
        self.view = self.ui.variantTree
        self.update_view()
        self.ui.tree_focus_changed.connect(self.update_view)

    def undo_timeout_start(self):
        self.undo_action_grp.setEnabled(False)
        self.undo_timer.start()

    def undo_timeout_stop(self):
        if not self.view.editor.enabled:
            self.undo_timer.start()
            return

        self.undo_action_grp.setEnabled(True)

    def search(self):
        self.search_dlg.center_on_ui()
        self.search_dlg.show()

    def select_references(self):
        self.view.editor.selection.select_references()

    def deselect(self):
        self.view.editor.selection.clear_selection()

    def copy(self):
        self.ui.clipboard.items = self.view.editor.copy_items()
        self.ui.clipboard.origin = self.view.editor.view

    def cut(self):
        self.copy()
        self.view.editor.remove_rows()

    def paste(self):
        if not self.ui.clipboard.items:
            return

        self.view.editor.paste_items(self.ui.clipboard)

    def remove_rows(self):
        self.view.editor.remove_rows()

    def toggle_history(self):
        if self.history.isHidden():
            self.history.show()
        else:
            self.history.hide()

    def update_view(self):
        self.view = self.ui.tree_with_focus()
