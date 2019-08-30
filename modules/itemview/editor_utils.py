from typing import List, Tuple

from PySide2.QtCore import QModelIndex, QUuid, Qt

from modules.idgen import KnechtUuidGenerator
from modules.itemview.item import KnechtItem
from modules.itemview.model import KnechtModel
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.itemview.model_update import UpdateModel
from modules.knecht_camera import KnechtImageCameraInfo
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class KnechtEditorUtilities:
    """ KnechtEditor static helper methods that need no access to the view property or other dynamic fields """
    def __init__(self, editor):
        """

        :param modules.itemview.editor.KnechtEditor editor:
        """
        self.editor = editor

    @classmethod
    def create_camera_item(cls, name: str, camera_info: dict):
        item = KnechtItem(None, ('', name, '', 'camera_item', '', KnechtUuidGenerator.create_id(),))

        for idx, (k, v) in enumerate(camera_info.items()):
            item.append_item_child(
                KnechtItem(item, (f'{idx:03d}', k, v, '', '', '', KnechtImageCameraInfo.rtt_camera_desc.get(k) or '', ))
                )
        return item

    @classmethod
    def insert_child_from_data(cls, model, parent, data):
        new_position = model.rowCount(parent)
        model.insertRow(new_position, parent)
        new_index = model.index(new_position, 0, parent)

        if data:
            cls.update_columns(model, new_index, parent, data)

        return new_index

    @classmethod
    def insert_child(cls, model: KnechtModel, parent, child: KnechtItem):
        position = child.childNumber()
        model.insertRows(position, 1, parent)
        new_index = model.index(position, 0, parent)

        cls.update_columns(model, new_index, parent, child.data_list())

        return new_index

    @staticmethod
    def new_empty_model(view):
        empty_model = KnechtModel()
        update_model = UpdateModel(view)
        update_model.update(empty_model)

    @staticmethod
    def update_columns(model, index: QModelIndex(), parent=None, column_data: list=list()) -> None:
        model.setDataList(index, column_data, parent)

    @staticmethod
    def get_item_children(item):
        if not item:
            return

        for child in item.iter_children():
            yield child

    @staticmethod
    def get_order_data(index: QModelIndex, order: int = 0) -> int:
        if not index.isValid():
            return 0

        if order == 0:
            order_data = index.siblingAtColumn(Kg.ORDER).data(Qt.DisplayRole)

            if order_data and order_data.isdigit():
                order = int(order_data)

        return order

    @classmethod
    def collect_referenced_items(cls, destination: int, different_origin: bool,
                                 view_origin, items: List[KnechtItem],
                                 src_model: KnechtModel) -> List[KnechtItem]:
        """ Collect referenced presets for copy+paste methods

        :param int destination: 0: top level of the tree 1: item level between children of an item 2: an empty item
        :param different_origin: copy to foreign tree view True/False
        :param KnechtTreeView view_origin: view the items originate from
        :param items:
        :param src_model:
        :return: referenced items
        """
        preset_items = list()
        created_ids = set()

        if not different_origin:
            # No need to search for references if pasting to the same tree
            return preset_items

        origin_src_model = view_origin.model().sourceModel()
        search_items = items
        recursion_limit, recursion_idx = 10, 0

        # Collect references recursive
        while recursion_idx <= recursion_limit:
            found_items = list()

            for item in cls._collect_references(search_items, origin_src_model, src_model, destination, created_ids):
                found_items.append(item)

            preset_items += found_items
            search_items = preset_items
            recursion_idx += 1

            if not found_items:
                break

        return preset_items

    @classmethod
    def _collect_references(cls, items: List[KnechtItem], origin_src_model: KnechtModel, src_model: KnechtModel,
                            destination: int, created_ids: set) -> List[KnechtItem]:
        # Collect
        for preset_item in cls._collect_referenced_presets(items, origin_src_model, destination):
            _id: QUuid = preset_item.preset_id

            # Skip unidentified and existing presets
            if not _id or src_model.id_mgr.is_id_existing_preset(_id):
                continue

            # Skip already created Id's
            if _id.toString() in created_ids:
                continue

            LOGGER.debug('Collecting referenced preset: %s', preset_item)
            created_ids.add(_id.toString())
            yield preset_item

    @classmethod
    def _collect_referenced_presets(cls, items: List[KnechtItem], src_model: KnechtModel,
                                    destination) -> List[KnechtItem]:
        for item in items:
            ref_id: QUuid = item.reference
            _id: QUuid = item.preset_id

            if destination > 0 and _id:
                # Add copied presets instead of just referenced ones if target is item level
                new_item = item.copy()
                yield new_item

            if ref_id:
                new_item = src_model.id_mgr.get_preset_from_id(ref_id).copy()
                yield new_item

            for child in item.iter_children():
                child_ref_id = child.reference

                if child_ref_id:
                    new_item = src_model.id_mgr.get_preset_from_id(child_ref_id).copy()
                    yield new_item

    @staticmethod
    def determine_destination(src_model, current_idx, dest_view, view_origin) -> Tuple[int, bool]:
        """
        Copy items to top level if top level is selected and selected item has children.

        If Item has no children and is therefore not selectable in it's sub-level,
        copy items to sub level.

        :param KnechtModel src_model: current tree view
        :param QModelIndex current_idx: currently selected index
        :param KnechtTreeView dest_view: destination view pasted too
        :param KnechtTreeView view_origin: tree view copied from
        :return Tuple[int, bool]: [Destination int 0 - item, 1 - top_level, 2 - empty item],
                                   [tree view is identical: True/False]
        """
        destination = 0  # Destination is top level of tree view
        destination = 1  # Destination is item which already has children
        destination = 2  # Destination is an empty top level item

        different_origin = True   # Destination is a different tree view.

        if src_model.is_top_level(current_idx):  # Is top level selected ?
            destination = 0                      # Destination is top level of tree view

            if current_idx.isValid():               # > Valid item selected.
                item = src_model.get_item(current_idx)

                if item.userType in [Kg.preset, Kg.render_preset]:
                    if item and not item.childCount():  # > Selected item has no children ?
                        destination = 2                 # > Destination is empty item!
        else:
            destination = 1

        if dest_view == view_origin:          # Destination and origin match?
            different_origin = False             # No different origin!

        return destination, different_origin

    @staticmethod
    def remove_duplicates(copied_items: List[KnechtItem], referenced_items: List[KnechtItem]) -> List[KnechtItem]:
        """ Remove collected references that have been copied as well """
        referenced_ids = list(map(lambda i: i.preset_id, [i for i in referenced_items]))
        copied_ids = list(map(lambda i: i.preset_id, [i for i in copied_items]))
        items = list()

        for idx, copied_id in enumerate(copied_ids):
            if copied_id not in referenced_ids:
                items.append(copied_items[idx])

        del copied_items
        return items

    def convert_clipboard(self, items: List[KnechtItem], src_index: QModelIndex,
                          src_model: KnechtModel, view_origin) -> List[KnechtItem]:
        """ When pasting to item level, convert top level items to references. """
        top_level_items = list()
        sub_level_items = list()

        origin_src_model = view_origin.model().sourceModel()

        # TODO: Convert top level Separator to Sub_Separator

        for item in items:
            new_item = item.copy(copy_children=False)

            if new_item.parent() == origin_src_model.root_item:
                # Convert top level items to references
                if new_item.userType != Kg.variant:
                    new_item.convert_to_reference()

                top_level_items.append(new_item)
            else:
                sub_level_items.append(new_item)

        top_level_items = self.reorder_item_order_data(top_level_items, src_index)
        sub_level_items = self.reorder_item_order_data(sub_level_items, src_index)

        return top_level_items + sub_level_items

    def reorder_item_order_data(self, item_ls: List[KnechtItem], src_index: QModelIndex):
        """ Re-write order column data based on the source_index to paste too and
            return sorted item list
        """
        # Order item list by order column values
        item_ls = self.editor.collect.order_items_by_order_column(item_ls)
        # Value to start with at paste target index
        new_order_value = self.get_order_data(src_index)

        for item in item_ls:
            item.setData(Kg.ORDER, f'{new_order_value:03d}')
            new_order_value += 1

        return item_ls
