from typing import Tuple

from PySide2 import QtWidgets
from PySide2.QtCore import QModelIndex, QObject, QTimer, Qt, Signal

from modules.globals import ITEM_WORK_CHUNK, ITEM_WORK_INTERVAL
from modules.itemview.model import KnechtModel
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


def get_current_parent_index(model, parent_idx, parent_position):
    new_parent_position = parent_position
    parent_row_count = model.rowCount(parent_idx.parent())
    if parent_position >= parent_row_count:
        new_parent_position = parent_row_count

    new_parent_idx = model.index(new_parent_position, 0, parent_idx.parent())
    if new_parent_idx.isValid():
        parent_idx = new_parent_idx

    return parent_idx


def get_current_index(model, parent_idx, parent_position, position,
                      debug: bool=False, log_txt: str = '') -> Tuple[QModelIndex, QModelIndex]:
    """
        Update the parent index - this preserves the correct parent index even
        if the parent has been deleted and undone.
        From the updated parent_idx, update the current index.
    """
    parent_idx = get_current_parent_index(model, parent_idx, parent_position)

    new_position = position
    parent_row_count = model.rowCount(parent_idx)
    if position >= parent_row_count:
        LOGGER.debug('Resetting position %s parent row count %s', position, parent_row_count)
        new_position = parent_row_count

    new_idx = model.index(new_position, 0, parent_idx)

    if debug:
        LOGGER.debug('%s at Row @%03d-P%03d Saved: @%03d-P@%03d[%s]',
                     log_txt, new_idx.row(), new_idx.parent().row(),
                     position, parent_idx.row(), parent_idx.isValid())

    return new_idx, parent_idx


class TreeUndoCommandChainWorker(QObject):
    debug = False
    started = Signal()
    finished = Signal()
    chunk_size = ITEM_WORK_CHUNK

    def __init__(self, undo_parent, view, started_callback=None, finished_callback=None):
        """
            Worker progresses through TreeChainCommand child commands
            and displays progress inside tree view.

            :param TreeChainCommand undo_parent: Parent QUndoCommand containing the work chunks as childs
            :param QTreeView view: The view we will edit and that holds the progress overlay
            :param started_callback: Callable to call by Signal on start of work event loop
            :param finished_callback: Callable to call by Signal after the work event loop
        """
        super(TreeUndoCommandChainWorker, self).__init__()

        self.undo_parent = undo_parent

        self._work_child_list = []
        self.current_work_is_undo = False

        self.work_timer = QTimer()
        self.work_timer.setInterval(ITEM_WORK_INTERVAL)
        self.work_timer.timeout.connect(self.work)

        if started_callback:
            self.started.connect(started_callback)

        if finished_callback:
            self.finished.connect(finished_callback)

        try:
            self.progressBar = view.progress
        except AttributeError:
            self.progressBar = QtWidgets.QProgressBar()

    def initialize_worker(self, is_undo):
        self.started.emit()
        self.log_chain_start(is_undo)

        self.current_work_is_undo = is_undo

        # Create child list ordered by their rows 2, 1, 0
        log_list = list()
        for child in self.iterate_children():
            log_list.append(child.position)
            self._work_child_list.append(child)

        if self.debug:
            LOGGER.debug('Command Chain Order: %s', log_list)

        if self.chunk_size > self.undo_parent.childCount():
            # No need to start the timer, start immediately.
            self.work()
            return

        self.update_view_progress(finished=False)
        self.work_timer.start()

    def work(self):
        work_range = min(self.chunk_size, len(self._work_child_list))

        for _ in range(work_range):
            if self.current_work_is_undo:
                child = self._work_child_list.pop(-1)
                child.undo()
            else:
                child = self._work_child_list.pop(0)
                child.redo()

        self.update_progress_bar(work_range)

        if not len(self._work_child_list):
            self.finished_work()

    def finished_work(self):
        self.work_timer.stop()
        self.update_view_progress(finished=True)
        self.finished.emit()

    def iterate_children(self):
        for c in range(self.undo_parent.childCount()):
            yield self.undo_parent.child(c)

    def update_view_progress(self, finished: bool=True) -> None:
        if not finished:
            # Init Progress Bar and disable View
            self.progressBar.setFormat('%v / %m')
            self.progressBar.setMaximum(self.undo_parent.childCount())
            self.progressBar.setValue(0)
            self.progressBar.show()
        else:
            # Hide Progress Bar and enable View
            self.progressBar.setFormat('')
            self.progressBar.hide()

    def update_progress_bar(self, num_items: int) -> None:
        """ Add number of items to existing value """
        self.progressBar.setValue(self.progressBar.value() + num_items)

    def log_chain_start(self, is_undo: bool) -> None:
        if not self.debug:
            return

        LOGGER.debug('#################################')
        txt = 'Redo'
        if is_undo:
            txt = 'Undo'
        LOGGER.debug('%s Chain started with %s items.', txt, self.undo_parent.childCount())


class TreeChainCommand(QtWidgets.QUndoCommand):
    def __init__(self, view, add, started_callback=None, finished_callback=None):
        """
        Holds multiple QUndoCommands as a chain of child Undo Commands.
        (command compression)

        Re/Undo will work down all children commands asynchronously
        """
        super(TreeChainCommand, self).__init__()
        self.view = view
        self.chain_worker = TreeUndoCommandChainWorker(self, view, started_callback, finished_callback)

        self.started = started_callback
        self.finished = finished_callback

        if add:
            self.txt = _("Elemente hinzufügen")
        else:
            self.txt = _("Elemente entfernen")

    def redo(self):
        self.chain_worker.initialize_worker(is_undo=False)

    def undo(self):
        self.chain_worker.initialize_worker(is_undo=True)

    """
    def redo(self):
        self.started()
        for cmd in self.iterate_children():
            cmd.redo()
        self.finished()

    def undo(self):
        self.started()
        for cmd in self.iterate_children(forward=False):
            cmd.undo()
        self.finished()

    def iterate_children(self, forward=True):
        if forward:
            for c in range(0, self.childCount()):
                yield self.child(c)
        else:
            for c in range(self.childCount()-1, -1, -1):
                yield self.child(c)
    """


class TreeCommand(QtWidgets.QUndoCommand):
    """
        This Command holds a single QUndoCommand to add or remove an item
        parented under the  TreeChainCommand
        (command compression)
    """
    def __init__(self, parent_cmd: TreeChainCommand, editor, index, model,
                 item=None, add: bool = True, parent_idx: QModelIndex=None):
        super(TreeCommand, self).__init__(parent_cmd)
        self.model = model
        self.item = item

        self.debug = TreeUndoCommandChainWorker.debug

        self.previous_remove_failed = False

        if not item:
            self.item = model.get_item(index)

        self.position = index.row()

        if parent_idx:
            self.parent_idx = parent_idx
        else:
            self.parent_idx = index.parent()

        self.parent_position = self.parent_idx.row()

        self.editor = editor
        self.add = add

    def redo(self):
        current_idx, new_parent_idx = self.get_current_index('Redo')

        if self.add:
            if self.previous_remove_failed:
                # Do not add item if previous remove failed
                self.previous_remove_failed = False
                return

            new_idx = self.editor.command_insert_row(self.model, current_idx, new_parent_idx, self.item)
            self.position = new_idx.row()
            self.parent_position = new_idx.parent().row()
        else:
            if not self.editor.command_remove_row(current_idx, self.model):
                self.previous_remove_failed = True
            self.item.setData(0, f'{int(self.item.data(0)) - 1:03d}')

        self.editor.iterator.order_items(new_parent_idx)

    def undo(self):
        current_idx, new_parent_idx = self.get_current_index('Undo')

        if self.add:
            if not self.editor.command_remove_row(current_idx, self.model):
                self.previous_remove_failed = True
        else:
            if self.previous_remove_failed:
                # Do not add item if previous remove failed
                self.previous_remove_failed = False
                return

            new_idx = self.editor.command_insert_row(self.model, current_idx, new_parent_idx, self.item)
            if self.debug:
                LOGGER.debug('Undo created new_idx @%03dP%03d', new_idx.row(), new_idx.parent().row())
            self.position = new_idx.row()
            self.parent_position = new_idx.parent().row()
            self.item.setData(0, f'{int(self.item.data(0)) + 1:03d}')

        self.editor.iterator.order_items(new_parent_idx)

    def get_current_index(self, txt):
        return get_current_index(self.model, self.parent_idx, self.parent_position, self.position, self.debug, txt)


class TreeOrderCommandChain(QtWidgets.QUndoCommand):
    def __init__(self, started_callback=None, finished_callback=None):
        super(TreeOrderCommandChain, self).__init__()
        self.started_callback = started_callback
        self.finished_callback = finished_callback

        self.txt = _('verschieben')

    def redo(self):
        self.started_callback()
        for cmd in self.iterate_children():
            cmd.redo()
        self.finished_callback()

    def undo(self):
        self.started_callback()
        for cmd in self.iterate_children():
            cmd.undo()
        self.finished_callback()

    def iterate_children(self):
        for c in range(self.childCount()):
            yield self.child(c)


class TreeOrderCommand(QtWidgets.QUndoCommand):
    def __init__(self, parent_cmd: TreeOrderCommandChain, editor, index: QModelIndex, new_order: int):
        """ Re-order items by re-writing the order column.

        :param parent_cmd:
        :param modules.itemview.editor.KnechtEditor editor:
        :param index:
        :param new_order:
        """
        super(TreeOrderCommand, self).__init__(parent_cmd)

        self.debug = TreeUndoCommandChainWorker.debug

        self.editor = editor
        self.new_order = new_order
        self.model: KnechtModel = index.model()
        self.position = index.row()
        self.parent_idx = index.parent()
        self.parent_position = index.parent().row()

        # Make sure index is in Order column
        self.index = self.model.sibling(index.row(), Kg.ORDER, index)

        self.current_order = int(self.index.data())

    def redo(self):
        current_idx, new_parent_idx = self.get_current_index('Redo')
        current_idx, new_order = self.move(self.new_order, current_idx, new_parent_idx)

        if self.debug:
            LOGGER.debug('Move Current Idx: @%03dP%03d from %s to %s[%s]',
                         current_idx.row(), current_idx.parent().row(),
                         self.current_order, new_order, self.new_order)

        self.model.setData(current_idx, f'{new_order:03d}', role=Qt.EditRole)
        self.editor.iterator.order_items(new_parent_idx)
        # self.model.refreshIndexData()

    def undo(self):
        # TODO: Critical error when re-ordering multiple selected items in renderTree
        current_idx, new_parent_idx = self.get_current_index('Undo')
        current_idx, new_order = self.move(self.current_order, current_idx, new_parent_idx)

        if self.debug:
            LOGGER.debug('Move Current Idx: @%03dP%03d from %s to %s[%s]',
                         current_idx.row(), current_idx.parent().row(),
                         self.new_order, new_order, self.current_order)

        self.model.setData(current_idx, f'{new_order:03d}', role=Qt.EditRole)
        self.editor.iterator.order_items(new_parent_idx)
        # self.model.refreshIndexData()

    def move(self, new_order: int, current_idx, new_parent_idx):
        move_one_below, move_up = self.editor.match.move_direction(new_order, current_idx, self.model)

        if move_one_below:
            if self.debug:
                LOGGER.debug('Detected movement one order below.')

            proxy_model = self.editor.view.model()
            current_prx_idx = proxy_model.mapFromSource(current_idx)
            index_below = proxy_model.sibling(current_prx_idx.row() + 1, Kg.ORDER, current_prx_idx)

            if index_below.isValid():
                src_index_below = proxy_model.mapToSource(index_below)
                return src_index_below, new_order - 2

        if move_up:
            if self.debug:
                LOGGER.debug('Detected movement in up direction.')
            return current_idx, new_order - 1

        return current_idx, new_order

    def get_current_index(self, txt):
        current_idx, new_parent_idx = get_current_index(self.model, self.parent_idx,
                                                        self.parent_position, self.position, self.debug, txt)

        self.parent_position = new_parent_idx.row()
        self.position = current_idx.row()
        return current_idx, new_parent_idx
