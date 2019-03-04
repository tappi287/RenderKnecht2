from PySide2.QtCore import QObject, QModelIndex, Slot, QEvent
from PySide2.QtWidgets import QUndoCommand

from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class ViewItemEditUndo(QObject):
    """
        Undo command for view item edits
    """
    def __init__(self, view):
        super(ViewItemEditUndo, self).__init__(parent=view)
        self.view = view
        self.undo_stack = view.undo_stack

        self.previous_data = ''
        self.edit_index = QModelIndex()
        self.reference_index_ls = list()

        self.org_view_edit = self.view.edit
        self.view.edit = self._item_edit_wrapper

        self.org_data_commit = self.view.commitData
        self.view.commitData = self._data_commit_wrapper

    @Slot(QModelIndex, object, QEvent)
    def _item_edit_wrapper(self, index, trigger, event):
        """ Fetch the start of an edit """
        self.org_view_edit(index, trigger, event)

        if trigger & self.view.editTriggers():
            # Save data previous to editing
            self.previous_data = index.data()
            # Save currently edited index
            self.edit_index = index

        # Do not fetch the Qt item edit method, continue
        return False

    def _data_commit_wrapper(self, editor):
        """ Fetch user edit data commits to the model """
        self.org_data_commit(editor)
        current_data = self.edit_index.data()

        if self.previous_data == current_data:
            # No change detected
            return

        # Editor undo cmd
        undo_cmd = ItemEditUndoCommand(self.previous_data, current_data, self.edit_index)

        self.undo_stack.push(undo_cmd)
        self.undo_stack.setActive(True)


class ItemEditUndoCommand(QUndoCommand):
    """ Undo Command holding user edits on items """
    def __init__(self, previous_data, current_data, index, parent_cmd=None, editing_done: bool = True):
        super(ItemEditUndoCommand, self).__init__(parent_cmd)
        self.index = index

        self.previous_data = previous_data
        self.current_data = current_data

        self.editing_done = editing_done

        self.setText(_("{0} ändern {1} ...")
                     .format(Kg.column_desc[self.index.column()], current_data[:15])
                     )

    def redo(self):
        self._do_children(is_undo=False)
        self._set_reference_data(self.index, self.current_data)

        if self.editing_done:
            # Do nothing on initial command creation
            return

        self._set_data(self.index, self.current_data)

    def undo(self):
        self._do_children(is_undo=True)

        self._set_reference_data(self.index, self.previous_data)
        self._set_data(self.index, self.previous_data)
        self.editing_done = False

    def _do_children(self, is_undo: bool):
        for c in range(self.childCount()):
            if is_undo:
                self.child(c).undo()
            else:
                self.child(c).redo()

    @staticmethod
    def _set_data(index, data):
        model = index.model()
        model.setData(index, data)

    @staticmethod
    def _set_reference_data(index, data):
        model = index.model()
        src_model = model.sourceModel()
        src_index = model.mapToSource(index)

        src_model.update_reference_data(src_index, data)
