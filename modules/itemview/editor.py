from typing import List

from PySide2.QtCore import QItemSelectionModel, QModelIndex, QObject, Qt
from PySide2.QtWidgets import QTreeView

from modules.itemview.editor_collect import KnechtCollectVariants
from modules.itemview.editor_copypaste import KnechtEditorCopyPaste
from modules.itemview.editor_iterate import KnechtIterateView
from modules.itemview.editor_match import KnechtMatchItems
from modules.itemview.editor_render_presets import KnechtEditorRenderPresets
from modules.itemview.editor_selection import KnechtItemSelection
from modules.itemview.editor_undo import TreeChainCommand, TreeCommand, TreeOrderCommand, TreeOrderCommandChain
from modules.itemview.editor_utils import KnechtEditorUtilities
from modules.itemview.item import KnechtItem
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class KnechtEditor(QObject):
    """
        View Editor to manipulate the model of a provided view with full undo/redo support
    """

    def __init__(self, view):
        super(KnechtEditor, self).__init__(view)
        self.view = view
        self.enabled = True

        # --- Helper objects ---
        self.match = KnechtMatchItems(self)
        self.iterator = KnechtIterateView(self)
        self.selection = KnechtItemSelection(self)
        self.copypaste = KnechtEditorCopyPaste(self)
        self.util = KnechtEditorUtilities(self)
        self.collect = KnechtCollectVariants(self.view)
        self.render = KnechtEditorRenderPresets(self)

        # --- Shortcuts ---
        self.get_current_selection = self.selection.get_current_selection
        self.get_selection = self.selection.get_selection
        self.clear_view_render_presets = self.render.clear_view_render_presets

        self.copy_items = self.copypaste.copy_items
        self.paste_items = self.copypaste.paste_items

        # Change current index to the item matching order column after undo cmd finished
        self.change_current_to = None

    def view_is_editable(self) -> bool:
        if not self.view.editTriggers():
            return False
        return True

    def report_current(self):
        sorted_rows, src_model = self.get_selection()
        proxy_model = self.view.model()

        LOGGER.debug('##### Current Selection #####')

        for index in sorted_rows:
            item = src_model.get_item(index)
            ref_intact = False

            if src_model.id_mgr.is_item_reference(item) and src_model.id_mgr.is_index_reference(index):
                ref_intact = True

            is_referenced_preset = src_model.id_mgr.is_item_referenced_preset(item)
            proxy_index = proxy_model.mapFromSource(index)
            LOGGER.debug(f'\n{item.data(Kg.NAME)[:10]}; Ref intact: {ref_intact}; Ref Preset: {is_referenced_preset}; '
                         f'Src @{index.row():03d}-P{index.parent().row():03d} '
                         f'Prx @{proxy_index.row():03d}-P{proxy_index.parent().row():03d}\n'
                         f'UserType: {item.userType}\n'
                         f'ID: {item.preset_id}\n'
                         f'Re: {item.reference}\n'
                         f'Or: {item.origin}')

    def create_top_level_rows(self, item_ls: List[KnechtItem], at_row: int=0,
                              undo_cmd_chain_override: TreeChainCommand=None):
        """ Create the provided list of items at top level """
        if not self.enabled:
            return

        current_src_index, src_model = self.get_current_selection()

        # -- Navigate to top level item
        while current_src_index.parent().isValid():
            current_src_index = current_src_index.parent()

        # -- Determine the order value behind current selection
        new_order_value = self.util.get_order_data(current_src_index, at_row)

        # -- Add UndoCmd's into provided override chain or create one
        if undo_cmd_chain_override:
            undo_cmd_chain = undo_cmd_chain_override
        else:
            undo_cmd_chain = self.create_undo_chain(add=True)

        for item in item_ls:
            # Update item order data
            item.setData(Kg.ORDER, f'{new_order_value:03d}')

            # Create undo command
            TreeCommand(undo_cmd_chain, self, QModelIndex(), src_model, item, add=True)

            new_order_value += 1

        # -- Prepare moving the current selection to the newly created item
        self.change_current_to = f'{max(0, new_order_value):03d}'

        if not undo_cmd_chain_override:
            # Request UndoCmd item creation if no override chain present
            self.undo_push_to_stack(undo_cmd_chain)

    def remove_rows(self, ignore_edit_triggers=False):
        """ Removes the currently selected rows (or entire model) - undoable """
        if not self.enabled or not self.view_is_editable():
            if not ignore_edit_triggers:
                return

        index_ls, model = self.get_selection()

        if not index_ls:
            return

        if self.selection.whole_tree_selected:
            self.clear_tree()
            return

        undo_cmd_chain = self.create_undo_chain(add=False)

        for index in index_ls:
            if index.parent() in index_ls:
                # Skip rows who will have their parent removed
                LOGGER.debug('Will not remove row which will have its parent deleted: %s', index.row())
                continue
            TreeCommand(undo_cmd_chain, self, index, model, add=False)

        self.undo_push_to_stack(undo_cmd_chain)

    def clear_tree(self):
        """ Update with empty model instead of chain deletion """
        if not self.enabled:
            return

        # Remove render presets from render tab on clear view
        self.view.view_cleared.emit(self.view)

        self.util.new_empty_model(self.view)

    def move_rows_keyboard(self, move_up: bool=False, jump: bool=False):
        proxy_index_ls: List[QModelIndex] = self.view.selectionModel().selectedRows()
        if not proxy_index_ls:
            return

        rows = [r.row() for r in proxy_index_ls]
        move_steps = 10 if jump else 1

        if move_up:
            first_idx = proxy_index_ls[rows.index(min(rows))]  # Index with smallest row number inside selection
            destination_row = max(0, first_idx.row() - move_steps)
            destination_idx = first_idx.siblingAtRow(destination_row)
        else:
            last_idx = proxy_index_ls[rows.index(max(rows))]  # Index with largest row number inside selection
            destination_row = min(self.view.model().rowCount(), last_idx.row() + move_steps)
            destination_idx = last_idx.siblingAtRow(destination_row)

        self.move_rows(destination_idx)

    def move_rows(self, destination_idx: QModelIndex):
        proxy_model = self.view.model()
        destination_src_idx = proxy_model.mapToSource(destination_idx)
        index_ls, src_model = self.get_selection()

        for index in index_ls:
            if index.parent() != destination_src_idx.parent():
                # Movement across different parents is not supported
                return

        destination_order = self.match.find_move_order(destination_idx, destination_src_idx,
                                                       proxy_model, src_model)

        undo_order_cmd_chain = TreeOrderCommandChain(self.undo_chain_start, self.undo_chain_finished)

        _, move_up = self.match.move_direction(destination_order, index_ls[-1], src_model)

        if not move_up:
            index_ls = index_ls[::-1]

        for index in index_ls:
            TreeOrderCommand(undo_order_cmd_chain, self, index, destination_order)

        self.undo_push_to_stack(undo_order_cmd_chain)

    def command_insert_row(self, model, index, parent, item=None, data: list = list()) -> QModelIndex:
        """
            Calling this method directly will -NOT- create an Undo command
            Use insert_rows, create_top_level_row instead
        """
        origin = None  # Copy item origin property
        if item:
            data = item.data_list()
            origin = item.origin

        if not model.insertRows(index.row(), 1, parent):
            # Case when parent has no children or index previous to Undo was 0
            new_index = self.util.insert_child_from_data(model, parent, data)
            LOGGER.debug('Inserted child @%03dP%03d', new_index.row(), new_index.parent().row())
        else:
            new_index = model.index(index.row(), 0, parent)
            self.util.update_columns(model, new_index, parent, data)

        for child in self.util.get_item_children(item):
            self.util.insert_child(model, new_index, child)

        new_item = model.get_item(new_index)
        if new_item:
            new_item.origin = origin

        return new_index

    def command_remove_row(self, index, model):
        """
            Calling this method directly will -NOT- create an Undo command
            Use remove_rows instead
        """
        # LOGGER.debug('Command Removing Row \t@%03d P%03d', index.row(), index.parent().row())
        if not model.removeRows(index.row(), 1, index.parent()):
            LOGGER.error('Could not remove Row %s!', index.row())

    def reset(self):
        self.view.model().sourceModel().reset()

    def _match_new_current(self) -> list:
        """
            Match new current item by its order column
            self.change_current_to contains the order to lookup as str
        """
        if not self.change_current_to:
            return []

        match = self.match.index(self.change_current_to, Kg.ORDER, QModelIndex())
        LOGGER.debug('Matched new index as current, for order: %s, %s', self.change_current_to, match)

        self.change_current_to = None
        return match

    def create_undo_chain(self, add):
        undo_cmd_chain = TreeChainCommand(self.view, add,
                                          started_callback=self.undo_chain_start,
                                          finished_callback=self.undo_chain_finished)
        return undo_cmd_chain

    def undo_push_to_stack(self, undo_chain_cmd):
        undo_chain_cmd.setText('{0} {1}'.format(undo_chain_cmd.childCount(), undo_chain_cmd.txt))
        self.view.undo_stack.push(undo_chain_cmd)

    def undo_chain_start(self):
        # self.view.undo_stack.setActive(False)
        self.view.model().clear_filter()
        self.enabled = False

    def undo_chain_finished(self):
        self.view.model().apply_last_filter()
        new_current = self._match_new_current()

        if new_current:
            self.view.selectionModel().setCurrentIndex(new_current,
                                                       (QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows))

        self.view.refresh()
        self.enabled = True
        # self.view.undo_stack.setActive(True)
