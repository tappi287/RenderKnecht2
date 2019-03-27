from typing import List, Union

from PySide2.QtCore import QAbstractItemModel, QModelIndex, QPersistentModelIndex, QRegExp, QSortFilterProxyModel, \
    QUuid, Qt, Slot

from modules.itemview.item import KnechtItem
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.itemview.model_uuid import KnechtModelIdentifiers
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class KnechtModel(QAbstractItemModel):
    default_roles = [Qt.DisplayRole, Qt.EditRole, Qt.DecorationRole,
                       Qt.ForegroundRole, Qt.FontRole, Qt.BackgroundRole]

    itemflags = dict(
        non_edit=Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled |
                 Qt.ItemIsDropEnabled,
        editable=Qt.ItemIsEditable | Qt.ItemIsEnabled | Qt.ItemIsSelectable |
                 Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled,
        )

    def __init__(self, root_item=None, silent: bool=False, checkable_columns: list=None):
        super(KnechtModel, self).__init__()
        self.root_item = root_item or self.create_root_item()

        self.id_mgr = KnechtModelIdentifiers(self)

        self.is_render_view_model = False

        self.supported_roles = self.default_roles[:]

        if checkable_columns:
            self.checkable_columns = tuple(checkable_columns)
            self.supported_roles.append(Qt.CheckStateRole)
        else:
            self.checkable_columns = tuple()

        # Only for use if no view is connected yet
        self.silent = silent

    @staticmethod
    def create_root_item():
        return KnechtItem()

    @Slot(QUuid, object, bool)
    def update_preset_id(self, _id, item: KnechtItem, add: bool):
        self.id_mgr.preset_id_changed(_id, item, add)

    @Slot(QUuid, object, bool, bool)
    def update_reference_id(self, _id, item: KnechtItem, add: bool, invalid: bool):
        self.id_mgr.reference_id_changed(_id, item, add, invalid)

    def is_top_level(self, index: QModelIndex) -> bool:
        if not index.parent().isValid():
            return True

        return False

    def get_index_from_item(self, item: KnechtItem) -> QModelIndex:
        if item is None or not item:
            return QModelIndex()

        parent_item = item.parent()

        if not parent_item:
            return QModelIndex()

        if parent_item == self.root_item:
            return self.index(item.childNumber(), 0)

        if parent_item.parent() == self.root_item:
            parent_idx = self.index(parent_item.childNumber(), 0)
            return self.index(item.childNumber(), 0, parent_idx)

        return QModelIndex()

    def get_index_from_persistent(self, persistent_index: QPersistentModelIndex) -> QModelIndex:
        return self.index(persistent_index.row(), persistent_index.column(), persistent_index.parent())

    def get_item(self, index):
        if index is not None and index.isValid():
            item = index.internalPointer()

            return item

        return self.root_item

    # ---- Overrides ----
    def columnCount(self, parent=QModelIndex(), *args, **kwargs):
        return Kg.column_count

    def data(self, index, role=None):
        if not index.isValid():
            return None

        if role not in self.supported_roles:
            return None

        item = self.get_item(index)

        if role == Qt.CheckStateRole and index.column() in self.checkable_columns:
            return Qt.Checked if item.isChecked(index.column()) else Qt.Unchecked

        return item.data(index.column(), role)

    def data_list(self, index, role=Qt.DisplayRole) -> Union[bool, list]:
        """ Returns data of every column as list """
        if not index.isValid():
            return False

        if role != Qt.DisplayRole and role != Qt.EditRole:
            return False

        item = self.get_item(index)
        return item.data_list()

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags

        item = self.get_item(index)
        flags = self.itemflags['editable']

        if not item.userType:
            return Qt.ItemIsSelectable

        # --- References ---
        if item.userType == Kg.reference and index.column() != Kg.NAME:
            flags = self.itemflags['non_edit']

        # --- Render Settings ---
        if item.userType == Kg.render_setting and index.column() != Kg.VALUE:
            flags = self.itemflags['non_edit']

        # --- Separator ---
        if item.userType in [Kg.separator, Kg.sub_separator]:
            flags = self.itemflags['non_edit']

        if index.column() == Kg.ORDER:
            flags = self.itemflags['non_edit']

        if index.column() in self.checkable_columns:
            flags = flags | Qt.ItemIsUserCheckable

        return flags

    def userType(self, index):
        if not index.isValid():
            return Qt.NoItemFlags

        item = self.get_item(index)

        return item.userType

    def index(self, row, column, parent=QModelIndex(), *args, **kwargs):
        """
            Changed from Qt Example Code because of match not finding child items with recursive match flag:
            https://forum.qt.io/topic/41977/solved-how-to-find-a-child-in-a-qabstractitemmodel/10
        """
        if not self.hasIndex(row, column, parent):
            return QModelIndex()

        parent_item = self.get_item(parent)
        child_item = parent_item.child(row)

        if child_item:
            return self.createIndex(row, column, child_item)
        else:
            return QModelIndex()

    def insertRows(self, position, rows, parent=QModelIndex(), *args, **kwargs):
        parent_item = self.get_item(parent)

        if not self.silent:
            self.beginInsertRows(parent, position, position + rows - 1)

        result = parent_item.insertChildren(position, rows,
                                            preset_id_method=self.update_preset_id,
                                            reference_id_method=self.update_reference_id)

        if not self.silent:
            self.endInsertRows()

        return result

    def parent(self, index=None):
        if index is None or not index.isValid():
            return QModelIndex()

        child_item = self.get_item(index)
        parent_item = child_item.parent()

        if not parent_item or parent_item == self.root_item:
            return QModelIndex()

        return self.createIndex(parent_item.childNumber(), 0, parent_item)

    def removeRows(self, row, count, parent=QModelIndex(), *args, **kwargs):
        parent_item = self.get_item(parent)

        self.beginRemoveRows(parent, row, row + count - 1)
        result = parent_item.removeChildren(row, count)
        self.endRemoveRows()

        return result

    def rowCount(self, parent=QModelIndex(), *args, **kwargs):
        parent_item = self.get_item(parent)

        return parent_item.childCount()

    def setDataList(self, index, value_list, parent=None, role=Qt.EditRole):
        if role != Qt.EditRole:
            return False

        if not index.isValid():
            return False

        if not parent:
            parent = index.parent()

        item = self.get_item(index)

        c = 0
        for c in Kg.column_range:
            if c >= len(value_list):
                break
            item.setData(c, value_list[c], role)

        end_index = self.index(index.row(), c, parent)

        if not self.silent:
            self.dataChanged.emit(index, end_index)

        return True

    def setData(self, index, value, role=Qt.EditRole):
        if role not in [Qt.EditRole, Qt.CheckStateRole] or value is None:
            return False

        item = self.get_item(index)

        result = item.setData(index.column(), value, role)

        if result and not self.silent:
            self.dataChanged.emit(index, index)

        return result

    def update_reference_data(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole or not value:
            return False

        results = list()

        for ref_index in self.id_mgr.get_all_links_from_index(index):
            # Change reference index column, id_mgr will always return indices with column 0
            ref_index = self.index(ref_index.row(), index.column(), ref_index.parent())

            # Update reference data
            results.append(self.setData(ref_index, value, role))

        if False in results:
            return False
        else:
            return True

    def _lastIndex(self):
        """
            Index of the very last item in the tree.
        """
        current_idx = QModelIndex()
        row_count = self.rowCount(current_idx)
        while row_count > 0:
            current_idx = self.index(row_count-1, 0, current_idx)
            row_count = self.rowCount(current_idx)
        return current_idx

    def refreshData(self):
        """ Updates the data on all nodes, but without having to perform a full reset. """
        # --- Report all IDs to Model Id Manager ---
        for item in self.root_item.iter_children():
            self.refresh_item_id_data(item)

        # --- Style and validate references ---
        self.validate_references()

        # --- Style referenced presets ---
        self.id_mgr.reset_recursive_items()

        for item in self.id_mgr.iterate_presets():
            item.style_valid()

            if self.id_mgr.is_item_referenced_preset(item):
                item.style_italic()

            self.id_mgr.get_recursive_items(item)
        self.style_recursive_items(self.id_mgr.recursive_items)

        # --- Refresh all item data ---
        for item in self.root_item.iter_children():
            self.refresh_item_data(item)

        LOGGER.debug('Refreshed model IDs and item data.')
        self.refreshIndexData()

    def refreshIndexData(self):
        """ Refresh the models index data without performing reference searches and ID checks """
        column_count = self.columnCount()
        top_left = self.index(0, 0, QModelIndex())
        bottom_left = self._lastIndex()
        bottom_right = self.sibling(bottom_left.row(), column_count - 1, bottom_left)

        self.dataChanged.emit(top_left, bottom_right)
        LOGGER.debug('Refreshed model indices r%sc%s, r%sc%s',
                     top_left.row(), top_left.column(), bottom_right.row(), bottom_right.column())

    def refresh_item_data(self, item: KnechtItem):
        """ Iterate item children and refresh data of the current item """
        # Refresh item data
        item.refreshData()

        # Iterate item children
        for child in item.iter_children():
            self.refresh_item_data(child)

    def refresh_item_id_data(self, item: KnechtItem):
        item.refresh_id_data()

        for item in item.iter_children():
            self.refresh_item_id_data(item)

    @staticmethod
    def style_recursive_items(recursive_ls):
        if not recursive_ls:
            return

        for item in recursive_ls:
            item.style_recursive()

    def validate_references(self):
        if self.is_render_view_model:
            return

        invalid_references = list()
        for item in self.id_mgr.iterate_references():
            self._validate_reference(item, invalid_references)

        for item in invalid_references:
            item.invalidate_reference()

    def _validate_reference(self, item: KnechtItem, invalid_reference_ls):
        reference = item.reference
        if not reference:
            return

        if not self.id_mgr.validate_reference(reference):
            invalid_reference_ls.append(item)
        else:
            item.style_italic()

    def initial_item_id_connection(self):
        """ This should only be called -ONCE- if the model was not populated with insert_children """
        for item in self.root_item.iter_children():
            self._connect_item_ids(item)

    def _connect_item_ids(self, item):
        self._connect_item_id(item)

        for item in item.iter_children():
            self._connect_item_ids(item)

    def _connect_item_id(self, item):
        item.preset_id_changed.connect(self.update_preset_id)
        item.reference_id_changed.connect(self.update_reference_id)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.root_item.data(section)

        return None

    def supportedDropActions(self):
        return Qt.CopyAction | Qt.MoveAction

    def sort(self, column, order=Qt.AscendingOrder):
        LOGGER.debug('Sorting called %s %s', column, order)

    def reset(self):
        self.beginResetModel()
        self.removeRows(0, self.rowCount())
        self.endResetModel()


class CustomTypeFilter:
    def __init__(self):
        super(CustomTypeFilter, self).__init__()
        # We will save each type filtered top-level row here
        self._filtered_parent_rows_cache = set()

        # The white list that will not be filtered
        # and can be accessed by the filter_item_types property
        self._filter_item_types: List[str] = list()
        self.filter_item_types: property = None

    @property
    def filter_item_types(self):
        """ White filter by item type description """
        return self._filter_item_types

    @filter_item_types.setter
    def filter_item_types(self, value: List[str]):
        self._filtered_parent_rows_cache = set()  # Clear filtered parent rows cache
        self._filter_item_types = value

    @filter_item_types.deleter
    def filter_item_types(self):
        self._filtered_parent_rows_cache = set()  # Clear filtered parent rows cache
        self._filter_item_types = list()

    def set_type_filter(self, filter_list: List[str]):
        """ Set the white list of item type descriptions to display
            eg. ['preset'] displays only items(and their children) whose type description is 'preset'
        """
        self.filter_item_types = filter_list

    def clear_type_filter(self):
        """ Reset the item type filtering, show all types """
        del self.filter_item_types

    def _filter_types(self, source_row, source_parent, data_ls) -> bool:
        """ Call from filterAcceptsRow to filter items by their type description """
        if not self.filter_item_types:
            return False

        """ Do not apply filter to children which will be filtered by the row cache. """
        if source_parent.isValid():
            return False

        # Apply type white filter to top level items
        if data_ls[Kg.TYPE] not in self.filter_item_types:
            self._filtered_parent_rows_cache.add(source_row)
            return True

        return False

    def _filter_types_children(self, source_parent):
        """ Call from filterAcceptsRow for children whose parents are type filtered """
        if source_parent.row() in self._filtered_parent_rows_cache:
            return True
        return False


class KnechtSortFilterProxyModel(CustomTypeFilter, QSortFilterProxyModel):
    default_filter_columns = [Kg.NAME, Kg.VALUE, Kg.TYPE, Kg.DESC]

    def __init__(self, view):
        super(KnechtSortFilterProxyModel, self).__init__()
        self.setParent(view)
        self.view = view

        self.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.setRecursiveFilteringEnabled(True)

        # We only filter column zero. Our custom filter will read all column data at once
        # rather than iterating every column
        self.setFilterKeyColumn(0)

        # Custom field for columns to search expression in
        self.filter_columns = self.default_filter_columns[::]

        self.last_filter = dict(regex=QRegExp(''), type_filter=list())

    def clear_filter(self):
        """ Clear filtering and save current filter """
        self.last_filter['regex'] = self.filterRegExp()
        self.last_filter['type_filter'] = self.filter_item_types

        self.clear_type_filter()
        self.setFilterRegExp('')

    def apply_last_filter(self):
        """ Re-apply last saved filter """
        self.filter_item_types = self.last_filter['type_filter']
        self.setFilterRegExp(self.last_filter['regex'])

    def filterAcceptsRow(self, source_row, source_parent):
        # ---- Filter child items whose parents are already type filtered ----
        if self._filter_types_children(source_parent):
            return False

        # ---- Grab item data for all columns ----
        data_ls = self.sourceModel().data_list(
                                                self.sourceModel().index(source_row, 0, source_parent)
                                               )
        if not data_ls:
            return False

        # ---- Top-level Type White list ----
        if self._filter_types(source_row, source_parent, data_ls):
            # Apply type filter to top level items
            return False

        # ---- Actual filtering for filter expression ----
        for column in self.filter_columns:
            if self.filterRegExp().indexIn(data_ls[column]) >= 0:
                return True

        return False

    def supportedDropActions(self):
        return Qt.CopyAction | Qt.MoveAction
