from typing import List, Union

from PySide2.QtCore import QModelIndex, QObject, Qt
from PySide2.QtWidgets import QTreeView

from modules.gui.clipboard import TreeClipboard
from modules.idgen import KnechtUuidGenerator as Kid
from modules.itemview.editor_undo import TreeChainCommand, TreeCommand
from modules.itemview.item import KnechtItem
from modules.itemview.model import KnechtModel
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.log import init_logging

LOGGER = init_logging(__name__)


class KnechtEditorCopyPaste(QObject):
    """ KnechtEditor Extension to copy to and paste from the ui clipboard """
    preset_creation_accepted_types = [Kg.preset, Kg.output_item, Kg.camera_item, Kg.plmxml_item,
                                      Kg.variant, Kg.reference]

    def __init__(self, editor):
        """ View model editor Copy & Paste extensions

        :param modules.itemview.editor.KnechtEditor editor:
        """
        super(KnechtEditorCopyPaste, self).__init__(editor)
        self.editor = editor

    @property
    def view(self) -> QTreeView:
        return self.editor.view

    def copy_items(self) -> Union[List[KnechtItem], None]:
        src_index_ls, src_model = self.editor.get_selection()

        if not src_index_ls:
            return

        copied_items = list()
        for index in reversed(src_index_ls):
            item = src_model.get_item(index)

            if item.userType == Kg.render_setting:
                # Skip Render Settings
                continue

            new_item = item.copy()
            copied_items.append(new_item)

        return copied_items

    def copy_preset_items_from_selection(self) -> Union[List[KnechtItem], None]:
        """  Pre-process: Create a user preset from selected items """
        copied_items = self.copy_items()

        if not copied_items:
            return

        copied_items = self._filter_accepted_item_types(copied_items,
                                                        self.preset_creation_accepted_types)

        src_index, src_model = self.editor.get_current_selection()

        child_items = self.editor.util.convert_clipboard(copied_items, src_index, self.editor.view)

        return child_items

    def _filter_accepted_item_types(self, items: List[KnechtItem],
                                    accepted_item_types: list=None) -> List[KnechtItem]:
        if not accepted_item_types:
            accepted_item_types = self.view.accepted_item_types

        if not accepted_item_types:
            # No filter set, return all items
            return items

        accepted_items = list()

        for item in items:
            if item.userType in accepted_item_types:
                accepted_items.append(item)

        return accepted_items

    def paste_items(self, clipboard: TreeClipboard, move_undo_chain=None):
        """ Paste items from the clipboard to the currently selected view or current_item

        1. We determine the origin treeview the item was copied from *view_origin: KnechtTreeView*

        2. We determine if we copy to a different treeview: *different_origin: bool=True/False*

        3. We determine if our destination is: *destination: int=0/1/2*
            0. top level of the tree
            1. item level between children of an item
            2. an empty item with no children

        4. If we encounter a differing origin, we copy the referenced_items that are referenced inside our
           copies aswell.

        5. We send items(our clipboard content) and referenced_items aswell as
           the view_origin and different_origin to our paste methods depending on the destination

        :param TreeClipboard clipboard: tree clipboard
        :param TreeChainCommand move_undo_chain: Override creation of new chain and use this override chain instead
        """
        if not self.editor.view_is_editable() and not self.editor.view.supports_drop:
            return

        view_origin, items = clipboard.origin, list(map(lambda i: i.copy(), [i for i in clipboard.items]))

        # Copy only accepted items for this view
        items = self._filter_accepted_item_types(items)

        if not items:
            return

        current_src_index, src_model = self.editor.get_current_selection()

        destination, different_origin = self.editor.util.determine_destination(
                                            src_model, current_src_index, self.view, view_origin
                                            )

        referenced_items = self.editor.util.collect_referenced_items(destination, different_origin,
                                                                     view_origin, items, src_model)
        items = self.editor.util.remove_duplicates(items, referenced_items)

        paste_args = (items, current_src_index, src_model, referenced_items,
                      different_origin, view_origin, move_undo_chain)

        # --- Overwrite Paste behaviour on Render Tree ---
        if self.view.is_render_view:
            self._paste_to_render_view(*paste_args)
            return

        if destination == 0:
            # Paste to Top Level
            self._paste_top_level(*paste_args)
        elif destination == 1:
            # Paste to Item Level
            self._paste_to_item(*paste_args)
        elif destination == 2:
            # Paste to Empty Top Level Item
            self._paste_to_empty_item(*paste_args)

    def _paste_to_render_view(self, items: List[KnechtItem], current_src_index: QModelIndex,
                              src_model: KnechtModel, referenced_items: List[KnechtItem],
                              different_origin: bool, view_origin, move_undo_chain):
        """ Paste/drop to renderTree will always create top level items without references """
        referenced_items = list()
        presets = list()
        render_presets = list()

        for item in items:
            if item.userType == Kg.render_preset:
                item.origin = view_origin
                render_presets.append(item)

            if item.userType == Kg.preset:
                preset = item.copy(copy_children=False)
                preset.convert_to_reference()
                presets.append(preset)

        if presets:
            render_preset = view_origin.editor.create.create_render_preset_from_items(presets)
            render_preset.origin = view_origin
            render_presets.append(render_preset)

        self._paste_top_level(render_presets, current_src_index, src_model, referenced_items, different_origin,
                              view_origin, move_undo_chain)

    def _paste_top_level(self, items: List[KnechtItem], current_src_index: QModelIndex,
                         src_model: KnechtModel, referenced_items: List[KnechtItem],
                         different_origin: bool, view_origin, move_undo_chain):
        """ Create top level items with new Id's and add referenced items as necessary """
        # Remove references when pasting to top level
        items = [i for i in items if i.userType != Kg.reference]

        for item in items:
            if move_undo_chain:
                continue

            if src_model.id_mgr.get_preset_from_id(item.preset_id):
                # Create new preset_id if id already exists
                item.setData(Kg.ID, Kid.create_id(), role=Qt.EditRole)

                # Rename if pasting to same tree
                if not different_origin:
                    item.update_name()
                else:
                    match = self.editor.match.index(item.data(Kg.NAME), Kg.NAME)
                    if match:
                        item.update_name()

        ordered_item_ls = self.editor.util.reorder_item_order_data(referenced_items + items, current_src_index)
        self.editor.create_top_level_rows(ordered_item_ls, undo_cmd_chain_override=move_undo_chain)

    def _paste_to_item(self, items: List[KnechtItem], current_src_index: QModelIndex,
                       src_model: KnechtModel, referenced_items: List[KnechtItem],
                       different_origin: bool, view_origin, undo_cmd_chain_override):
        """ Convert copied items to item children and add referenced items as necessary """
        if not undo_cmd_chain_override:
            undo_cmd_chain = self.editor.create_undo_chain(add=True)
        else:
            undo_cmd_chain = undo_cmd_chain_override

        converted_items = self.editor.util.convert_clipboard(items + referenced_items, current_src_index, view_origin)

        for item in converted_items:
            TreeCommand(undo_cmd_chain, self.editor, current_src_index, src_model, item, add=True)

        if different_origin:
            self._create_collected_reference_presets(undo_cmd_chain, referenced_items)

        if not undo_cmd_chain_override:
            self.editor.undo_push_to_stack(undo_cmd_chain)

    def _paste_to_empty_item(self, items: List[KnechtItem], current_src_index: QModelIndex,
                             src_model: KnechtModel, referenced_items: List[KnechtItem],
                             different_origin: bool, view_origin, undo_cmd_chain_override):
        """ Swap the selected childless item with a newly created one with children.
            Convert copied items to item children and add referenced items as necessary
        """
        if not undo_cmd_chain_override:
            undo_cmd_chain = self.editor.create_undo_chain(add=True)
        else:
            undo_cmd_chain = undo_cmd_chain_override

        # Add clipboard items as children
        for item in self.editor.util.convert_clipboard(items + referenced_items, current_src_index, view_origin):
            TreeCommand(undo_cmd_chain, self.editor, current_src_index, src_model,
                        item, add=True, parent_idx=current_src_index)

        if different_origin:
            self._create_collected_reference_presets(undo_cmd_chain, referenced_items)

        if not undo_cmd_chain_override:
            self.editor.undo_push_to_stack(undo_cmd_chain)

    def _create_collected_reference_presets(self, undo_cmd_chain, preset_items):
        """ Create the preset items referenced from our copied items """
        if preset_items:
            self.editor.create_top_level_rows(preset_items, undo_cmd_chain_override=undo_cmd_chain)
