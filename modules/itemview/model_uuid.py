from typing import Iterable, Iterator, Tuple, Union, List

from PySide2.QtCore import QModelIndex, QObject, QSortFilterProxyModel, QUuid, Slot

from modules.idgen import is_valid_uuid
from modules.itemview.item import KnechtItem
from modules.knecht_utils import search_list_indices
from modules.log import init_logging

LOGGER = init_logging(__name__)


class IdStorage:
    def __init__(self):
        self.items = list()
        self.ids = list()

        self.search_list_indices = search_list_indices

    def add(self, _id: QUuid, item: KnechtItem):
        self.items.append(item)
        self.ids.append(_id)

    def iterate_children(self):
        yield from self.children

    def get_id(self, item: KnechtItem) -> Union[QUuid, None]:
        """ Return the uuid matching item """
        if item not in self.items:
            return

        idx = self.items.index(item)
        return self.ids[idx]

    def get_item(self, _id: QUuid) -> Union[KnechtItem, None]:
        """ Return the first item matching _id """
        if _id not in self.ids:
            return

        idx = self.ids.index(_id)
        return self.items[idx]

    def get_all_items_by_id(self, _id) -> Iterable[KnechtItem]:
        """ Return all items matching _id """
        item_list = list()

        # Iterate every list index this id is stored in
        for idx in self.search_list_indices(self.ids, _id):
            item = self.items[idx]
            item_list.append(item)

        return item_list

    def remove_item(self, item: KnechtItem) -> bool:
        if item not in self.items:
            return False

        idx = self.items.index(item)
        self.items.pop(idx)
        self.ids.pop(idx)

        return True

    def remove_id(self, _id: QUuid) -> bool:
        if _id not in self.ids:
            return False

        idx = self.ids.index(_id)
        self.items.pop(idx)
        self.ids.pop(idx)

        return True

    def has_item(self, item) -> bool:
        if item in self.items:
            return True
        return False

    def has_id(self, _id) -> bool:
        if _id in self.ids:
            return True
        return False

    def has_items(self) -> bool:
        if self.items:
            return True
        return False

    def item_iterator(self) -> Iterator[KnechtItem]:
        yield from self.items

    def id_iterator(self) -> Iterator[QUuid]:
        yield from self.ids


class KnechtModelIdentifiers(QObject):
    debug_preset = False
    debug_ref = False

    check_recurring_id = QUuid()

    def __init__(self, parent_model):
        """ ID Manager stores item identifiers for the parent model

        :param modules.itemview.model.KnechtModel parent_model:
        """
        super(KnechtModelIdentifiers, self).__init__(parent=parent_model)
        self.model = parent_model

        self._presets = IdStorage()
        self._references = IdStorage()
        self.invalid_references = IdStorage()
        self.recursive_items = list()

    def preset_id_changed(self, _id: QUuid, item: KnechtItem, add: bool) -> None:
        """ Preset Ids updated from model """
        # -- Remove from Id storage --
        if not add:
            self._presets.remove_item(item)
            if self.debug_preset:
                LOGGER.debug(f'Removed Preset {_id.toString()[-5:-1]}['
                             f'{len(self._presets.items):02d}] - {item.data(0)[:3]}{item.data(1)[:10]} - {self.model}')

            return

        # -- Add to Id storage --
        if is_valid_uuid(_id):
            self._presets.add(_id, item)

            if self.debug_preset:
                LOGGER.debug(f'Added Preset {_id.toString()[-5:-1]}['
                             f'{len(self._presets.items):02d}] - {item.data(0)[:3]}{item.data(1)[:10]} - {self.model}')

    def reference_id_changed(self, _id: QUuid, item: KnechtItem, add: bool, invalid: bool=False) -> None:
        """ Reference Ids updated from model """
        # -- Add invalid reference --
        if invalid and add:
            self.invalid_references.add(_id, item)
            if self.debug_ref:
                LOGGER.debug(f'Adding invalid Reference {_id.toString()[-5:-1]}['
                             f'{len(self.invalid_references.items):02d}] {item.data(1)[:10]} - {self.model}')
        # -- Remove invalid reference --
        elif invalid and not add:
            self.invalid_references.remove_item(item)
            if self.debug_ref:
                LOGGER.debug(f'Removing from invalid References ['
                             f'{len(self.invalid_references.items):02d}] {item.data(1)[:10]} - {self.model}')
        # -- Remove from Id storage --
        elif not invalid and not add:
            self._references.remove_item(item)

            if self.debug_ref:
                LOGGER.debug(f'Removed Reference {_id.toString()[-5:-1]}['
                             f'{len(self._references.items):02d}] {item.data(1)[:10]} - {self.model}')
        # -- Add to Id storage --
        elif not invalid and add:
            self.invalid_references.remove_item(item)

            self._references.add(_id, item)

            if self.debug_ref:
                LOGGER.debug(f'Added Reference {_id.toString()[-5:-1]}['
                             f'{len(self._references.items):02d}] - {item.data(1)[:10]} - {self.model}')

    def is_item_referenced_preset(self, preset: KnechtItem) -> bool:
        if self._references.has_id(preset.preset_id):
            return True
        return False

    def is_item_reference(self, reference: KnechtItem) -> bool:
        if self._references.has_item(reference):
            return True
        return False

    def is_index_referenced_preset(self, index: QModelIndex) -> bool:
        item = self.model.get_item(index)

        if item and self._references.has_id(item.preset_id):
            return True

        return False

    def is_index_reference(self, index: QModelIndex):
        item = self.model.get_item(index)

        if item and self._references.has_item(item):
            return True

        return False

    def is_id_existing_preset(self, _id: QUuid):
        return self._presets.has_id(_id)

    def has_invalid_references(self) -> bool:
        return self.invalid_references.has_items()

    def has_recursive_items(self) -> bool:
        if self.recursive_items:
            return True
        return False

    def iterate_presets(self):
        return self._presets.item_iterator()

    def iterate_references(self):
        return self._references.item_iterator()

    def iterate_invalid_references(self):
        return self.invalid_references.item_iterator()

    def iterate_recursive_items(self):
        yield from self.recursive_items

    def validate_reference(self, _id):
        if not self._presets.get_item(_id):
            return False
        return True

    def get_preset_id_from_index(self, preset_index: QModelIndex) -> Union[QUuid, None]:
        item = self.model.get_item(preset_index)
        if item:
            return item.preset_id

    def get_reference_id_from_index(self, preset_index: QModelIndex) -> Union[QUuid, None]:
        item = self.model.get_item(preset_index)
        if item:
            return item.reference

    def get_preset_from_reference_index(self, index: QModelIndex) -> Union[None, KnechtItem]:
        referenced_id = self.get_reference_id_from_index(index)
        return self._presets.get_item(referenced_id)

    def get_references_from_preset_index(self, index: QModelIndex) -> Iterable[KnechtItem]:
        preset_id = self.get_preset_id_from_index(index)
        return self._references.get_all_items_by_id(preset_id)

    def get_references_from_id(self, _id):
        return self._references.get_all_items_by_id(_id)

    def get_preset_from_id(self, _id):
        return self._presets.get_item(_id)

    def get_invalid_references_indices(self, proxy_model: QSortFilterProxyModel=None):
        """ Get indices to all invalid references """
        return self._convert_items_to_indices(self.iterate_invalid_references(), proxy_model)

    def get_recursive_indices(self, proxy_model: QSortFilterProxyModel=None):
        """ Get indices to all recursive references """
        return self._convert_items_to_indices(self.iterate_recursive_items(), proxy_model)

    def get_references_by_indices(self,
                                  index_list: Iterable[QModelIndex],
                                  proxy_model: QSortFilterProxyModel = None,
                                  ) -> Tuple[Iterable[QModelIndex], Iterable[QModelIndex]]:
        """ Get referenced presets and reference indices.

            Provide a list of model indices and get two separate lists
            containing:

            * all referenced preset items linked from the provided reference indices
            * all reference items linking to the provided preset indices

            *IMPORTANT* The returned indices will have their column at 0

            :param Iterable[QModelIndex] index_list: the indices to look up
            :param QSortFilterProxyModel proxy_model: the proxy model the results should be mapped to

            :rtype  Tuple[Iterable[QModelIndex], Iterable[QModelIndex]]: (list(), list())
            :returns : Tuple with list of referenced Presets and list of reference indices.
        """
        reference_items = list()
        referenced_presets = list()

        # --- Collect referenced items ---
        for index in index_list:
            if self.is_index_referenced_preset(index):
                reference_items += self.get_references_from_preset_index(index)
                continue

            if self.is_index_reference(index):
                referenced_presets.append(self.get_preset_from_reference_index(index))

        reference_index_ls = [idx for idx in self._convert_items_to_indices(reference_items, proxy_model)]
        preset_index_ls = [idx for idx in self._convert_items_to_indices(referenced_presets, proxy_model)]

        return preset_index_ls, reference_index_ls

    def get_all_links_from_index(self, index: QModelIndex):
        """ Get *all* indices that have the same id as the provided index

            *IMPORTANT* The returned indices will have their column at 0

            :returns Iterable[QModelIndex]: All references and presets with matching id
        """
        linked_items = list()

        if self.is_index_referenced_preset(index):
            linked_items += self.get_references_from_preset_index(index)

        if self.is_index_reference(index):
            reference_id = self.get_reference_id_from_index(index)

            linked_items += self.get_references_from_id(reference_id)
            linked_items.append(self.get_preset_from_id(reference_id))

        index_ls = [idx for idx in self._convert_items_to_indices(linked_items)]

        if index in index_ls:
            index_ls.remove(index)

        return index_ls

    def reset_recursive_items(self):
        self.recursive_items = list()

    def get_recursive_items(self, preset) -> List[Tuple[KnechtItem, KnechtItem]]:
        """ Check every know preset in the model for recursive references.

        :returns [ (KnechtItem, KnechtItem) ]: List containing recursive preset item and
                                               child item causing the recursion as pair inside a tuple.
        """
        self.check_recurring_id = preset.preset_id

        recursive_preset, recursive_child = self._check_preset(preset, 0)

        if recursive_preset or recursive_child:
            if recursive_preset not in self.recursive_items:
                self.recursive_items.append(recursive_preset)
            if recursive_child not in self.recursive_items:
                self.recursive_items.append(recursive_child)

        return self.recursive_items

    def _check_preset(self, preset: KnechtItem, depth: int=0
                      ) -> Union[Tuple[KnechtItem, KnechtItem], Tuple[None, None]]:
        if depth > 10:
            return None, None

        for child in preset.iter_children():
            ref_id = child.reference

            if not isinstance(ref_id, QUuid):
                continue

            if ref_id == self.check_recurring_id:
                return preset, child

            referenced_preset = self.get_preset_from_id(ref_id)

            if referenced_preset:
                depth += 1
                recursive_preset, recursive_child = self._check_preset(referenced_preset, depth)

                if recursive_preset:
                    return recursive_preset, recursive_child

        return None, None

    def _convert_items_to_indices(self,
                                  items: Iterable[KnechtItem],
                                  proxy_model: QSortFilterProxyModel = None
                                  ) -> Iterator[QModelIndex]:
        for item in items:
            index = self.model.get_index_from_item(item)

            proxy_index = None
            if proxy_model:
                proxy_index = proxy_model.mapFromSource(index)

            if proxy_index:
                yield proxy_index
                continue

            if index:
                yield index
