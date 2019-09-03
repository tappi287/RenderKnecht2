import time
from typing import List

from PySide2.QtCore import QModelIndex, QTimer, Qt, Signal, Slot
from PySide2.QtWidgets import QAbstractItemView, QLineEdit, QMenu, QTreeView, QUndoGroup, QUndoStack, QWidget, \
    QApplication

from modules.globals import UNDO_LIMIT
from modules.gui.animation import BgrAnimation
from modules.gui.ui_overlay import InfoOverlay
from modules.gui.widgets.progress_overlay import ProgressOverlay, ShowTreeViewProgressMessage
from modules.itemview.delegates import KnechtValueDelegate
from modules.itemview.editor import KnechtEditor
from modules.itemview.item_edit_undo import ViewItemEditUndo
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.itemview.tree_dragdrop import KnechtDragDrop
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
    view_cleared = Signal(object)
    view_refreshed = Signal()
    clean_changed = Signal(bool, object)
    reset_missing = Signal()

    block_timeout = 60000

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
        self.supports_drop = True
        self.supports_drag_move = True

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

        # Filter typing time
        self.filter_timer = QTimer()
        self.filter_timer.setSingleShot(True)
        self.filter_timer.setInterval(500)
        self.filter_timer.timeout.connect(self._set_filter_from_timer)

        # Cache last applied filter
        self._cached_filter = str()

        # Setup view properties
        # Permanent type filter for eg. renderTree
        self.__permanent_type_filter = []
        self.__permanent_type_filter_column = Kg.TYPE

        # Render Tree
        self.__is_render_view = False

    @property
    def is_render_view(self):
        return self.__is_render_view

    @is_render_view.setter
    def is_render_view(self, val: bool):
        self.__is_render_view = val

    @property
    def permanent_type_filter_column(self):
        return self.__permanent_type_filter_column

    @permanent_type_filter_column.setter
    def permanent_type_filter_column(self, val: int):
        self.__permanent_type_filter_column = val

    @property
    def permanent_type_filter(self):
        """ Apply a permanent item type description white filter to this view """
        return self.__permanent_type_filter

    @permanent_type_filter.setter
    def permanent_type_filter(self, val: List[str]):
        self.__permanent_type_filter = val

        if self.model() is not None:
            self.model().type_filter_column = self.__permanent_type_filter_column

        if val:
            # Apply filtering if filter has values
            self.apply_permanent_type_filter(True, self.__permanent_type_filter)
        else:
            # Disable filtering if filter no values
            self.apply_permanent_type_filter(False, self.__permanent_type_filter)

    @permanent_type_filter.deleter
    def permanent_type_filter(self):
        self.__permanent_type_filter = list()
        self.apply_permanent_type_filter(False, self.__permanent_type_filter)

    @property
    def filter_text_widget(self):
        return self._filter_text_widget

    @filter_text_widget.setter
    def filter_text_widget(self, widget: QLineEdit):
        self._filter_text_widget = widget
        self._filter_text_widget.textEdited.connect(self.set_filter_widget_text)

        bg_color = (255, 255, 255, 255)
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

        self.view_refreshed.emit()

    def clear_tree(self):
        if not self.model():
            return

        src_model = self.model().sourceModel()
        if src_model.rowCount():
            # Replace with empty tree model undoable
            self.editor.clear_tree()

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
        self.filter_timer.start()

    @Slot()
    def _set_filter_from_timer(self):
        self._set_filter(self.filter_text_widget.text())

    def _set_filter(self, txt: str):
        self.filter_bgr_animation.blink()
        txt = txt.replace(' ', '|')
        self.model().setFilterRegExp(txt)

        self._cached_filter = txt
        self.filter_expand_timer.start()

    def quick_view_filter(self, enabled: bool):
        self.apply_permanent_type_filter(enabled, Kg.QUICK_VIEW_FILTER)

    def apply_permanent_type_filter(self, enabled: bool, white_filter_list: list):
        prx_model = self.model()

        if enabled:
            prx_model.set_type_filter(white_filter_list)
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

    def block_until_editor_finished(self):
        """ When adding or removing items via undo_chain this method can block until
            the editor returned from the undo chain.
        """
        start = time.time()

        while not self.editor.enabled:
            QApplication.processEvents()
            if time.time() - start > self.block_timeout:
                break
