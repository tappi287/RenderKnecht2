from typing import List

from PySide2.QtCore import QModelIndex, QTimer, Qt, Signal, Slot
from PySide2.QtWidgets import QAbstractItemView, QLineEdit, QTreeView, QUndoGroup, QUndoStack, QWidget, QMenu

from modules.globals import UNDO_LIMIT
from modules.gui.animation import BgrAnimation
from modules.gui.tree_dragdrop import KnechtDragDrop
from modules.gui.ui_overlay import InfoOverlay
from modules.gui.widgets.progress_overlay import ProgressOverlay, ShowTreeViewProgressMessage
from modules.itemview.delegates import KnechtValueDelegate
from modules.itemview.editor import KnechtEditor
from modules.itemview.item_edit_undo import ViewItemEditUndo
from modules.itemview.model import KnechtSortFilterProxyModel
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.itemview.tree_view_utils import setup_header_layout
from modules.language import get_translation
from modules.log import init_logging
from modules.settings import KnechtSettings

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class KnechtTreeView(QTreeView):
    internalDrop = Signal(QTreeView, QModelIndex)
    view_cleared = Signal(object)
    clean_changed = Signal(bool, object)
    reset_missing = Signal()

    def __init__(self, parent: QWidget, undo_group: QUndoGroup):
        super(KnechtTreeView, self).__init__(parent)

        # -- Setup progress overlay
        self.progress_overlay = ProgressOverlay(self)
        self.progress = self.progress_overlay.progress

        # Setup tree view progress bar helper
        self.progress_msg = ShowTreeViewProgressMessage(self)

        # -- Add an undo stack to the view
        self.undo_stack = QUndoStack(undo_group)
        self.undo_stack.setUndoLimit(UNDO_LIMIT)

        self.undo_stack.cleanChanged.connect(self.view_clean_changed)

        # -- Item Edit undo
        self.edit_undo = ViewItemEditUndo(self)

        # -- Setup tree settings
        self.setAllColumnsShowFocus(True)
        self.setUniformRowHeights(True)
        self.setSortingEnabled(False)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setAlternatingRowColors(True)

        # -- Drag n Drop
        self.setAcceptDrops(True)
        self.setDragDropMode(QTreeView.DragDrop)

        self.drag_drop = KnechtDragDrop(self)

        # -- Filter items types this view accepts on paste/drop actions
        self.accepted_item_types = []  # Default accept all

        # Model Editor
        self.editor = KnechtEditor(self)

        # Reset missing signal
        self.editor.collect.reset_missing.connect(self.reset_missing)

        # Item Delegate for Value edits
        self.setItemDelegateForColumn(Kg.VALUE, KnechtValueDelegate(self))

        # Info Overlay
        self.info_overlay = InfoOverlay(self)

        # Context Menu
        self.context = QMenu(self)

        # Filter line edit widget to send keyboard input to
        self._filter_text_widget: QLineEdit = None
        self.filter_bgr_animation: BgrAnimation = None

        # Filter Expand timer, expand filtered items after timeout
        self.filter_expand_timer = QTimer()
        self.filter_expand_timer.setSingleShot(True)
        self.filter_expand_timer.setInterval(300)
        self.filter_expand_timer.timeout.connect(self.filter_expand_results)

        # Cache last applied filter
        self._cached_filter = str()

        # Setup view properties
        # Permanent type filter for eg. renderTree
        self.__permanent_type_filter = []

        # Render Tree
        self.__is_render_view = False

    @property
    def is_render_view(self):
        return self.__is_render_view

    @is_render_view.setter
    def is_render_view(self, val: bool):
        self.__is_render_view = val

    @property
    def permanent_type_filter(self):
        """ Apply a permanent item type description white filter to this view """
        return self.__permanent_type_filter

    @permanent_type_filter.setter
    def permanent_type_filter(self, val: List[str]):
        self.__permanent_type_filter = val

    @property
    def filter_text_widget(self):
        return self._filter_text_widget

    @filter_text_widget.setter
    def filter_text_widget(self, widget: QLineEdit):
        self._filter_text_widget = widget
        self._filter_text_widget.textEdited.connect(self.set_filter_widget_text)

        bg_color = (255, 255, 255)
        if KnechtSettings.app['app_style'] == 'fusion-dark':
            bg_color = KnechtSettings.dark_style['bg_color']
        self.filter_bgr_animation = BgrAnimation(self._filter_text_widget, bg_color)

    def current_filter_text(self) -> str:
        if not self.filter_text_widget:
            return ''

        return self.filter_text_widget.text()

    def refresh(self):
        if not self.model():
            return

        src_model = self.model().sourceModel()
        src_model.refreshData()

        if self.is_render_view:
            src_model.is_render_view_model = True

        if src_model.id_mgr.has_invalid_references():
            self.editor.selection.highlight_invalid_references()
        if src_model.id_mgr.has_recursive_items():
            self.editor.selection.highlight_recursive_indices()

        if self.permanent_type_filter:
            self.model().set_type_filter(self.permanent_type_filter)

    def clear_tree(self):
        if not self.model():
            return

        src_model = self.model().sourceModel()
        if src_model.rowCount():
            # Replace with empty tree model undoable
            self.editor.clear_tree()

            # Remove render presets from render tab on clear view
            self.view_cleared.emit(self)

            # Make sure we have focus after model update
            self.setFocus(Qt.OtherFocusReason)

    def sort_tree(self):
        setup_header_layout(self)

    @Slot(str)
    def set_filter_widget_text(self, filter_text: str):
        if not self.filter_text_widget:
            return

        if filter_text == self._cached_filter:
            # Skip filtering if eg. view tab changed but re-applied filter text is identical to last used filter
            return

        self.filter_text_widget.setText(filter_text)
        self.filter_bgr_animation.blink()
        self._set_filter(filter_text)

    @Slot(str)
    def _set_filter(self, txt: str):
        self.model().setFilterWildcard(txt)
        self._cached_filter = txt
        self.filter_expand_timer.start()

    def quick_view_filter(self, enabled: bool):
        prx_model = self.model()

        if enabled:
            prx_model.set_type_filter(Kg.QUICK_VIEW_FILTER)
        else:
            prx_model.clear_type_filter()

        # Re-apply filter to de-/activate type filtering
        prx_model.clear_filter()
        prx_model.apply_last_filter()

    @Slot()
    def filter_expand_results(self):
        prx_model = self.model()
        if prx_model.filterRegExp().isEmpty():
            return

        for row in range(0, prx_model.rowCount()):
            idx = prx_model.index(row, 1, QModelIndex())

            if not self.isExpanded(idx):
                self.expand(idx)

    def clear_filter(self):
        """
            Clear the current filter, collapse all items, expand selections and current index.
            Re-Apply permanent type filtering.

            If called a second time without a prior filter set. Collapse items and do not highlight selections.
            Eg. when user hits Esc twice to collapse all items.
        """
        LOGGER.debug('Clearing filter: %s', self.model().filterRegExp())

        if not self.model().filterRegExp().isEmpty():
            # Expand and highlight current selection if we return from a filter action
            highlight_selection = True
        else:
            # Collapse all items if no previous filter set
            highlight_selection = False

        self.model().clear_filter()
        self.collapseAll()

        if highlight_selection:
            self.editor.selection.highlight_selection()

        if self.filter_text_widget:
            self.filter_text_widget.setText('')

        if self.__permanent_type_filter:
            self.model().set_type_filter(self.__permanent_type_filter)
            self.model().clear_filter()
            self.model().apply_last_filter()

    @Slot(bool)
    def view_clean_changed(self, clean: bool):
        LOGGER.debug('Reporting changed Tree View Clean state')
        self.clean_changed.emit(clean, self)
