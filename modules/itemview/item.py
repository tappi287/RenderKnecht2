import re
from typing import Union

from PySide2.QtCore import QObject, Qt, Signal, QUuid
from PySide2.QtGui import QColor, QBrush, QFont

from modules.idgen import KnechtUuidGenerator as Kid
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.gui.ui_resource import IconRsc, FontRsc
from modules.log import init_logging

LOGGER = init_logging(__name__)


class ItemStyleDefaults:
    black = QBrush(QColor(15, 15, 15))
    grey = QBrush(QColor(150, 150, 150))
    red = QBrush(QColor(190, 90, 90))

    transparent_white = QBrush(QColor(255, 255, 255, 0))

    bg_white = QBrush(QColor(255, 255, 255), Qt.SolidPattern)
    bg_red = QBrush(QColor(231, 80, 80, 50), Qt.SolidPattern)

    variant_invalid_color = QBrush(QColor(255, 229, 229, 120), Qt.SolidPattern)
    variant_valid_color = QBrush(QColor(232, 255, 229, 120), Qt.SolidPattern)
    variant_default_color = QBrush(QColor(255, 255, 255, 0), Qt.SolidPattern)


class KnechtItem(QObject):
    preset_id_changed = Signal(QUuid, object, bool)
    reference_id_changed = Signal(QUuid, object, bool, bool)

    # Empty data
    empty = [None for x in Kg.column_range]
    # Default font color
    foreground = [None for x in Kg.column_range]
    # Default order column font color
    foreground[Kg.ORDER] = ItemStyleDefaults.grey
    # Default background
    background = [None for x in Kg.column_range]

    font = [FontRsc.regular for x in Kg.column_range]

    def __init__(self, parent_item=None, data: tuple=tuple(), preset_id_method=None, reference_id_method=None):
        super(KnechtItem, self).__init__()
        self.parentItem = parent_item

        self.itemData = {
            Qt.DisplayRole: KnechtItem.empty[:],
            Qt.DecorationRole: KnechtItem.empty[:],
            Qt.ForegroundRole: KnechtItem.foreground[:],
            Qt.FontRole: KnechtItem.font[:],
            Qt.BackgroundRole: KnechtItem.background[:],
            Qt.CheckStateRole: KnechtItem.empty[:],
            }

        if data:
            for idx, column in enumerate(data):
                self.itemData[Qt.DisplayRole][idx] = column

        if preset_id_method:
            # Will inform model of assigned preset uuid
            self.preset_id_changed.connect(preset_id_method)
        if reference_id_method:
            # Will inform model of assigned reference preset uuid
            self.reference_id_changed.connect(reference_id_method)

        # --- Set header data ---
        if not self.parentItem and not data:
            self.itemData[Qt.DisplayRole] = Kg.column_desc

        # --- Prepare child storage ---
        self.childItems = []
        self.num_children = 0

        # --- userType property ---
        self._userType = 0
        # --- Reference link uuid ---
        self._ref_id = None
        # --- Unique Preset Item Id ---
        self._preset_id = None
        # --- View Origin attribute ---
        self.__origin = None
        # --- User Type independent of type column ---
        self.fixed_userType = 0

    @property
    def userType(self):
        if self.fixed_userType:
            return self.fixed_userType
        return self._userType

    @userType.setter
    def userType(self, val):
        self._userType = val

    @property
    def origin(self):
        """
            Information from which view or model this item originates from.
            Used for renderPresets to link contents to their original model+view or clean
            them up upon view/model deletion.
        """
        return self.__origin

    @origin.setter
    def origin(self, val):
        self.__origin = val

    @property
    def reference(self):
        return self._ref_id

    @reference.setter
    def reference(self, val: QUuid):
        if self._ref_id:
            # Delete existing entry
            self.reference_id_changed.emit(self._ref_id, self, False, False)

        self._ref_id = val

        if val:
            # Create entry
            self.reference_id_changed.emit(val, self, True, False)

    @property
    def preset_id(self):
        return self._preset_id

    @preset_id.setter
    def preset_id(self, val: QUuid):
        if self._preset_id:
            # Delete existing entry
            self.preset_id_changed.emit(self._preset_id, self, False)

        self._preset_id = val

        if val:
            # Create entry
            self.preset_id_changed.emit(val, self, True)

    def remove_ids(self):
        """ Remove all children ids """
        self.preset_id = None
        # Delete existing invalid entry
        self.reference_id_changed.emit(self._ref_id, self, False, True)
        self.reference = None

        for c in self.iter_children():
            c.remove_ids()

    def convert_to_reference(self) -> bool:
        """ Do not call this if the item is inside a model! """

        # Update reference
        _id = Kid.create_id(self.preset_id)
        self.reference = _id
        self.setData(Kg.ID, '')
        self.setData(Kg.REF, _id)

        # Delete Preset ID
        self.preset_id = None

        return True

    def child(self, row):
        if row < 0 or row >= self.num_children or not self.num_children:
            return False

        return self.childItems[row]

    def iter_children(self):
        if not self.num_children:
            return list()

        yield from self.childItems

    def childCount(self):
        return self.num_children

    def childNumber(self):
        if self.parentItem is not None:
            if self in self.parentItem.childItems:
                return self.parentItem.childItems.index(self)
        return 0

    def columnCount(self):
        return Kg.column_count

    def setChecked(self, column: int, checkstate: int):
        return self.setData(column, checkstate, Qt.CheckStateRole)

    def isChecked(self, column: int):
        if self.data(column, Qt.CheckStateRole) == Qt.Checked:
            return True
        return False

    def data(self, column, role=Qt.DisplayRole):
        if role == Qt.EditRole:
            role = Qt.DisplayRole

        return self.itemData[role][column]

    def data_list(self):
        """ Returns data of every column as list summary """
        return self.itemData[Qt.DisplayRole]

    def append_item_child(self, child_item):
        child_item.parentItem = self
        self.childItems.append(child_item)
        self.num_children += 1

    def insertChildren(self, position, count, *args, **kwargs):
        if position < 0 or position > self.num_children:
            return False

        data = tuple()

        for row in range(count):
            if args:
                data = args[row]

            item = KnechtItem(self, data,
                              preset_id_method=kwargs.get('preset_id_method'),
                              reference_id_method=kwargs.get('reference_id_method'))
            if kwargs.get('fixed_userType'):
                item.fixed_userType = kwargs.get('fixed_userType')

            self.childItems.insert(position, item)
            self.num_children += 1

        return True

    def update_name(self):
        new_name = ItemRename.do(self.data(Kg.NAME))
        self.setData(Kg.NAME, new_name)

    def copy(self, copy_children: bool=True, new_parent=None):
        # Create new item
        if not new_parent:
            new_item = KnechtItem(self.parentItem, self.data_list())
        else:
            new_item = KnechtItem(new_parent, self.data_list())

        new_item.preset_id = self.preset_id
        new_item.reference = self.reference
        new_item.userType = self.userType
        new_item.origin = self.origin

        # Copy children
        if copy_children:
            self.copy_children(new_item)

        return new_item

    def copy_children(self, parent_item):
        new_children = list()

        for child in self.iter_children():
            new_children.append(child.copy(new_parent=parent_item))

        parent_item.childItems = new_children
        parent_item.num_children = len(new_children)

    def parent(self):
        return self.parentItem

    def removeChildren(self, position, count):
        if position < 0 or position + count > self.num_children:
            return False

        for row in range(count):
            child = self.childItems[position]

            child.remove_ids()  # Remove all children ids recursively
            self.childItems.pop(position)
            self.num_children -= 1

        return True

    def invalidate_reference(self):
        """ The referenced item is missing, mark reference invalid """
        # Add invalid reference to model id manager
        self.reference_id_changed.emit(self.reference, self, True, True)

        self.reference = None
        self.style_regular()
        self.style_missing()

    def refresh_id_data(self):
        """ Inform model id manager of item id's """
        self.setData(Kg.REF, self.data(Kg.REF))
        self.setData(Kg.ID, self.data(Kg.ID))

    def refreshData(self):
        for role, column_data in self.itemData.items():
            for column, data_value in enumerate(column_data):
                if column in (Kg.ID, Kg.REF):
                    continue

                result = self.setData(column, data_value, role)

                if not result:
                    LOGGER.error('Could not refresh Item Data: %s %s %s', column, data_value, role)

    def setData(self, column, value, role=Qt.DisplayRole):
        if role == Qt.EditRole:
            role = Qt.DisplayRole

        if role == Qt.DisplayRole:
            self._set_display_role_data(column, value)

        self.itemData[role][column] = value
        return True

    def _set_display_role_data(self, column, value):
        # --- Style by Type ---
        if column == Kg.TYPE:
            KnechtItemStyle.style_column(self, item_type_key=value)

        # --- Update Uuid ---
        if column in [Kg.REF, Kg.ID] and value:
            self.itemData[Qt.DisplayRole][column] = self.update_uuid(column, value)

        # Set User Type if all relevant columns have been filled
        if column > Kg.TYPE:
            KnechtItemUserType.set_user_type(self)

    def update_uuid(self, column, id_value):
        if not Kid.is_quuid(id_value):          # Test if value is QUuid object instance
            id_value = Kid.create_id(id_value)

        # Re-Set QUuid from valid QUuid if string is invalid Id
        if column == Kg.REF:
            self.reference = id_value
            self.style_valid()

        elif column == Kg.ID:
            self.preset_id = id_value
            self.style_regular()

        return id_value

    def style_regular(self):
        KnechtItemStyle.style_row(self, Qt.FontRole, FontRsc.regular)

    def style_italic(self):
        KnechtItemStyle.style_row(self, Qt.FontRole, FontRsc.italic)

    def style_valid(self):
        KnechtItemStyle.style_row(self, Qt.ForegroundRole, self.foreground[Kg.NAME])
        self.itemData[Qt.BackgroundRole] = self.empty[:]

    def style_unlocked(self):
        self.style_regular()
        KnechtItemStyle.style_row(self, Qt.ForegroundRole, ItemStyleDefaults.black)

    def style_locked(self):
        KnechtItemStyle.style_row(self, Qt.ForegroundRole, ItemStyleDefaults.grey)

    def style_missing(self):
        KnechtItemStyle.style_row(self, Qt.ForegroundRole, ItemStyleDefaults.red)

    def style_recursive(self):
        KnechtItemStyle.style_row(self, Qt.BackgroundRole, ItemStyleDefaults.bg_red)


class ItemRename:
    rename_count = 0

    @classmethod
    def do(cls, name: str) -> str:
        # Match anything in group 1(^.*)
        # match one or more(+) digits(\d) with leading underscore(_) at end of name($)
        pattern = r'(^.*)_(\d+$)'
        match = re.match(pattern, name)

        if not match:
            return f'{name}_001'

        item_numbering = int(match.group(match.lastindex))
        item_numbering += 1
        return f'{match.group(max(0, match.lastindex - 1))}_{item_numbering:03d}'


class KnechtItemUserType:

    @classmethod
    def set_user_type(cls, item: KnechtItem) -> None:
        item_type = cls.get_item_type(item)

        if item_type:
            item.userType = Kg.xml_tag_user_type.get(item_type)

    @classmethod
    def get_item_type(cls, item: KnechtItem) -> str:
        if item.data(Kg.REF):
            return 'reference'

        item_type_desc = item.data(Kg.TYPE)

        if item_type_desc in Kg.TYPE_MAPPING:
            return Kg.TYPE_MAPPING[item_type_desc]

        if item.data(Kg.ID) and item_type_desc:
            return 'preset'

        return 'variant'


class KnechtItemStyle:
    # Map Item type description to Icon Keys
    ICON_MAP = {
        'trim_setup': 'car',
        'fakom_setup': 'fakom_trim',
        'fakom_option': 'fakom',
        'options': 'options',
        'package': 'pkg',
        'reset': 'reset',
        'viewset': 'viewset',
        'viewset_mask': 'viewset_mask',
        'preset': 'preset',
        'preset_mask': 'preset_mask',
        'preset_ref': 'preset_ref',
        'OPT': 'img', 'COL': 'img',
        'RAD': 'img_free', 'SWL': 'img_free', 'SEA': 'img_free',
        'render_preset': 'render',
        'sampling': 'render',
        'file_extension': 'render',
        'resolution': 'render',
        'copy': 'copy',
        'checkmark': 'checkmark',
        'output_item': 'folder',
        'camera_item': 'videocam',
        'plmxml_item': 'assignment',
        }

    @classmethod
    def style_column(cls, item: KnechtItem, item_type_key: str=None, column: int=0) -> None:
        item_type_key = item_type_key or item.data(Kg.TYPE)

        if not column:
            column = Kg.style_column

        if item_type_key not in cls.ICON_MAP.keys():
            return

        if item.data(column, Qt.DecorationRole):
            return

        icon_key = cls.ICON_MAP[item_type_key]
        icon = IconRsc.get_icon(icon_key)

        item.itemData[Qt.DecorationRole][column] = icon

    @classmethod
    def style_row(cls, item: KnechtItem, role, style_data: Union[QBrush, QFont]) -> None:
        for column in Kg.column_range:
            item.itemData[role][column] = style_data
