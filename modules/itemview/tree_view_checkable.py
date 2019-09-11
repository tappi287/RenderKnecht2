from PySide2.QtCore import QEvent, QObject, Qt
from PySide2.QtWidgets import QAction, QLineEdit, QMenu, QTreeView, QUndoGroup, QWidget

from modules.gui.gui_utils import replace_widget
from modules.gui.ui_resource import IconRsc
from modules.itemview.model import KnechtModel
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.itemview.model_update import UpdateModel
from modules.itemview.tree_view import KnechtTreeView
from modules.itemview.tree_view_utils import KnechtTreeViewShortcuts
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class KnechtTreeViewCheckable(KnechtTreeView):
    def __init__(self, parent: QWidget, undo_group: QUndoGroup, replace: QTreeView=None, filter_widget: QLineEdit=None):
        """ Convenience class for Dialogs needing a checkable, un-editable view

        :param parent:
        :param undo_group:
        :param replace:
        :param filter_widget:
        """
        super(KnechtTreeViewCheckable, self).__init__(parent, undo_group)

        if replace:
            self.replace_view(replace)

        # Setup filter widget
        if filter_widget:
            self.filter_text_widget = filter_widget

        # Setup keyboard shortcuts
        self.shortcuts = KnechtTreeViewShortcuts(self)
        self.context = CheckableViewContext(self)

        # Setup un-editable
        self.setEditTriggers(QTreeView.NoEditTriggers)
        self.supports_drop = False
        self.supports_drag_move = False
        self.setDragDropMode(QTreeView.NoDragDrop)

    def replace_view(self, old_view):
        """ Replace an existing placeholder view """
        replace_widget(old_view, self)

        # Update with placeholder Model to avoid access to unset attributes
        UpdateModel(self).update(KnechtModel())

        # most Dialogs do not require a column description
        self.setHeaderHidden(True)

    def check_items(self, check_items: list, column: int,
                    check_all: bool=False, check_none: bool=False, check_selected: bool=False):
        selected_indices, src_model = self.editor.selection.get_selection_top_level()

        for (src_index, item) in self.editor.iterator.iterate_view(column=column):
            value, new_value = item.data(column, role=Qt.DisplayRole), None

            if value in check_items or item in check_items or check_all:
                new_value = Qt.Checked
            elif check_none:
                new_value = Qt.Unchecked
            elif check_selected:
                if src_index.siblingAtColumn(Kg.ORDER) in selected_indices:
                    new_value = Qt.Checked
                else:
                    new_value = Qt.Unchecked

            src_model.setData(src_index, new_value, Qt.CheckStateRole)


class CheckableViewContext(QMenu):
    def __init__(self, view: KnechtTreeViewCheckable):
        super(CheckableViewContext, self).__init__('Tree_Context', view)

        self.select_all = QAction(IconRsc.get_icon('check_box'), _('Alle Einträge auswählen'))
        self.select_all.triggered.connect(self.select_all_items)
        self.select_selected = QAction(IconRsc.get_icon('navicon'), _('Selektierte Einträge auswählen'))
        self.select_selected.triggered.connect(self.select_selected_items)
        self.select_none = QAction(IconRsc.get_icon('check_box_empty'), _('Alle Einträge abwählen'))
        self.select_none.triggered.connect(self.select_no_items)

        self.addActions([self.select_all, self.select_selected, self.select_none])

        self.view = view
        self.view.installEventFilter(self)

    def select_all_items(self):
        self.view.check_items([], self.get_column(), check_all=True)

    def select_selected_items(self):
        self.view.check_items([], self.get_column(), check_selected=True)

    def select_no_items(self):
        self.view.check_items([], self.get_column(), check_none=True)

    def get_column(self) -> int:
        src_model = self.view.model().sourceModel()

        if src_model.checkable_columns:
            return src_model.checkable_columns[0]

        return 0

    def eventFilter(self, obj: QObject, event: QEvent):
        if obj != self.view:
            return False

        if event.type() == QEvent.ContextMenu:
            self.popup(event.globalPos())
            return True

        return False
