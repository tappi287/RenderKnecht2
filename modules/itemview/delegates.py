from PySide2.QtCore import Qt, QModelIndex, QRegExp
from PySide2.QtGui import QRegExpValidator
from PySide2.QtWidgets import QStyledItemDelegate, QComboBox

from modules.itemview.item import KnechtItem
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class KnechtValueDelegate(QStyledItemDelegate):
    def __init__(self, view):
        """ Basic item delegate that returns the views default item delegate or depending
            on the item type column: an appropriate custom render setting item delegate.

        :param modules.itemview.treeview.KnechtTreeView view: View we replace delegates in
        """
        super(KnechtValueDelegate, self).__init__(view)
        self.view = view

        self.default_delegate = QStyledItemDelegate(view)
        self.setting_delegate = None

    def createEditor(self, parent, option, index):
        # ---- Default behaviour ----
        if not self._index_is_render_setting(index):
            return self.default_delegate.createEditor(parent, option, index)

        # ---- Custom behaviour ----
        return self.setting_delegate.create_editor(parent, option, index)

    def setEditorData(self, editor, index):
        # ---- Default behaviour ----
        if not self._index_is_render_setting(index):
            return self.default_delegate.setEditorData(editor, index)

        # ---- Custom behaviour ---
        self.setting_delegate.set_editor_data(editor, index)

    def setModelData(self, editor, model, index):
        # ---- Default behaviour ----
        if not self._index_is_render_setting(index):
            return self.default_delegate.setModelData(editor, model, index)

        # ---- Custom behaviour ---
        self.setting_delegate.set_model_data(editor, model, index)

    def updateEditorGeometry(self, editor, option, index):
        # ---- Default behaviour ----
        if not self._index_is_render_setting(index):
            return self.default_delegate.updateEditorGeometry(editor, option, index)

        # ---- Custom behaviour ---
        editor.setGeometry(option.rect)

    def _index_is_render_setting(self, index: QModelIndex):
        src_index = index.model().mapToSource(index)
        item: KnechtItem = index.model().sourceModel().get_item(src_index)
        setting_type = item.data(Kg.TYPE)

        if item.userType == Kg.render_setting and setting_type in RENDER_SETTING_MAP.keys():
            self.setting_delegate = RENDER_SETTING_MAP[setting_type](self.view)
            return True
        return False


class ComboBoxDelegate:
    @staticmethod
    def set_editor_data(editor: QComboBox, index):
        current_value = index.model().data(index, Qt.EditRole)
        current_index = 0

        for idx in range(0, editor.count()):
            value = editor.itemText(idx)

            if value == current_value:
                current_index = idx

        editor.setCurrentIndex(current_index)

    @staticmethod
    def set_model_data(editor: QComboBox, model, index):
        value = editor.currentText()

        model.setData(index, value, Qt.EditRole)


class SamplingComboBox(KnechtValueDelegate, ComboBoxDelegate):
    sampling_values = list()

    for s in range(0, 12+1):
        sampling_values.append(
            str(2 ** s)
            )

    def create_editor(self, parent, option, index):
        editor = QComboBox(parent)
        current_value = index.model().data(index, Qt.EditRole)
        current_index = 0

        for idx, value in enumerate(self.sampling_values):
            if current_value == value:
                current_index = idx
            editor.addItem(value)

        editor.setCurrentIndex(current_index)

        return editor


class ResolutionComboBox(KnechtValueDelegate, ComboBoxDelegate):
    resolution_values = ['1080 1080', '1280 720', '1280 960', '1920 1080', '1920 1440', '2560 1920',
                         '2880 1620', '3840 2160', '4096 2160']

    regex = QRegExp('^\d{1,4}\s{1}\d{1,4}$')
    regex.setCaseSensitivity(Qt.CaseInsensitive)
    validator = QRegExpValidator(regex)

    def create_editor(self, parent, option, index):
        editor = QComboBox(parent)
        editor.setEditable(True)
        editor.setValidator(self.validator)
        current_value = index.model().data(index, Qt.EditRole)
        current_index = 0

        for idx, value in enumerate(self.resolution_values):
            if current_value == value:
                current_index = idx
            editor.addItem(value)

        editor.setCurrentIndex(current_index)

        if current_value not in self.resolution_values:
            editor.addItem(current_value)
            editor.setCurrentIndex(editor.count())

        return editor


class FileExtensionComboBox(KnechtValueDelegate, ComboBoxDelegate):
    ext_values = ['.exr', '.hdr', '.png', '.jpg', '.bmp', '.tif']

    def create_editor(self, parent, option, index):
        editor = QComboBox(parent)
        current_value = index.model().data(index, Qt.EditRole)
        current_index = 0

        for idx, value in enumerate(self.ext_values):
            if current_value == value:
                current_index = idx
            editor.addItem(value)

        editor.setCurrentIndex(current_index)

        return editor


RENDER_SETTING_MAP = {
    'sampling': SamplingComboBox,
    'resolution': ResolutionComboBox,
    'file_extension': FileExtensionComboBox,
    }
