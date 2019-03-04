from typing import Union

from PySide2.QtCore import QMimeData, QObject, Qt, QItemSelectionModel, QModelIndex
from PySide2.QtGui import QDragMoveEvent, QDropEvent

from modules.gui.clipboard import TreeClipboard
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class KnechtDragDrop(QObject):
    clear_select_current_flags = (QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)

    def __init__(self, view):
        """ KnechtTreeView Helper class to handle item drag and drop

        :param modules.gui.main_ui.KnechtWindow ui:
        :param modules.itemview.treeview.self.view.__class__ view:
        """
        super(KnechtDragDrop, self).__init__(view)
        self.view = view

        # Create a drag n drop specific clipboard
        self.clipboard = TreeClipboard()

        # Overwrite tree drop event
        view.dropEvent = self.drop_event
        view.dragMoveEvent = self.drag_move_event

    def drag_move_event(self, e: QDragMoveEvent):
        src = e.source()

        if isinstance(src, self.view.__class__):
            e.setDropAction(Qt.MoveAction)

            if src is not self.view:
                e.setDropAction(Qt.CopyAction)

            if e.keyboardModifiers() == Qt.ShiftModifier:
                e.setDropAction(Qt.CopyAction)

            e.accept(self.view.rect())

    def drop_event(self, e: QDropEvent):
        mime: QMimeData = e.mimeData()
        src = e.source()

        if not isinstance(src, self.view.__class__):
            e.ignore()
            return

        e.setDropAction(Qt.MoveAction)

        if src is not self.view:
            e.setDropAction(Qt.CopyAction)

        if e.keyboardModifiers() == Qt.ShiftModifier:
            e.setDropAction(Qt.CopyAction)

        # -- Copy drop --
        if e.dropAction() is Qt.CopyAction:
            destination_index = self.view.indexAt(e.pos())
            self.copy_drop(src, destination_index)
            e.accept()

        if e.dropAction() is Qt.MoveAction:
            destination_index = self.view.indexAt(e.pos())
            self.move_drop(destination_index)

            # Ignore default view behaviour
            e.ignore()

    def move_drop(self, destination_index: QModelIndex):
        LOGGER.debug('Drop with MoveAction at Proxy @%sP%s', destination_index.row(), destination_index.parent().row())

        self.view.editor.move_rows(destination_index)

    def copy_drop(self, source_view, destination_index):
        LOGGER.debug('Drop with CopyAction at @%sP%s', destination_index.row(), destination_index.parent().row())

        result = self._copy(source_view)

        if not result:
            return

        self._select_drop_index(destination_index)

        self._paste()

    def _select_drop_index(self, destination_index: QModelIndex):
        """ Select current row or clear selection """
        if not destination_index.isValid():
            src_model = self.view.model().sourceModel()
            last_index = self.view.editor.match.find_highest_order_index(src_model)

            if not last_index:
                self.view.editor.selection.clear_selection()
                return

            destination_index = last_index

        self.view.selectionModel().setCurrentIndex(destination_index, self.clear_select_current_flags)

    def _paste(self):
        self.view.editor.paste_items(self.clipboard)

    def _copy(self, source_view) -> bool:
        item_copies = source_view.editor.copy_items()

        if not item_copies:
            return False

        self.clipboard.items = item_copies
        self.clipboard.origin = source_view

        return True
