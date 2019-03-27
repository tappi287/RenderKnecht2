from PySide2.QtCore import Qt, QRect, QPoint, QModelIndex
from PySide2.QtWidgets import QWidget, QPushButton, QComboBox, QLineEdit, QLabel, QDialog, QUndoCommand

from modules.itemview.item_edit_undo import ItemEditUndoCommand
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.globals import Resource
from modules.gui.gui_utils import SetupWidget
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class SearchDialog(QDialog):
    default_width = 600
    default_height = 100

    default_match_flags = Qt.MatchRecursive | Qt.MatchContains | Qt.MatchCaseSensitive

    def __init__(self, ui):
        """ Dialog to search and replace inside document views

        :param modules.gui.main_ui.KnechtWindow ui: Main Window
        """
        super(SearchDialog, self).__init__(ui)
        SetupWidget.from_ui_file(self, Resource.ui_paths['knecht_search'])
        self.ui = ui

        self.setWindowTitle(_('Suchen und Ersetzen'))
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        # --- Setup and translate Ui widgets ---
        self.btn_find: QPushButton
        self.btn_find.setText(_('Finden'))
        self.btn_find.released.connect(self.search)

        self.btn_replace: QPushButton
        self.btn_replace.setText(_('Ersetzen'))
        self.btn_replace.released.connect(self.search_replace)

        self.btn_replace_all: QPushButton
        self.btn_replace_all.setText(_('Alle Ersetzen'))
        self.btn_replace_all.released.connect(self.search_replace_all)

        self.column_box: QComboBox
        self.edit_replace: QLineEdit
        self.edit_search: QLineEdit
        self.lbl_replace: QLabel
        self.lbl_replace.setText(_('Ersetzen'))
        self.lbl_search: QLabel
        self.lbl_search.setText(_('Suchen'))
        self.lbl_column: QLabel
        self.lbl_column.setText(_('Spalte'))

        self.populate_column_box()

    def populate_column_box(self):
        for idx, c in enumerate(Kg.column_desc):
            if idx in (Kg.ORDER, Kg.REF, Kg.ID):
                continue
            self.column_box.addItem(c, userData=idx)

        self.column_box.setCurrentIndex(0)

    def center_on_ui(self):
        r: QRect = self.ui.frameGeometry()
        center = QPoint(r.x() + r.width() / 2, r.y() + r.height() / 2)
        top_left = QPoint(center.x() - self.default_width / 2, center.y() - self.default_height / 2)
        self.setGeometry(QRect(top_left.x(), top_left.y(), self.default_width, self.default_height))

    def search(self):
        txt = self.edit_search.text()
        column = self.column_box.currentData()

        view = self.ui.tree_with_focus()

        # --- Skip empty searches ---
        if not txt:
            return list(), view

        proxy_index_list = view.editor.match.indices(txt, column, match_flags=self.default_match_flags)

        if proxy_index_list:
            view.editor.selection.clear_and_select_proxy_index_ls(proxy_index_list)
            view.editor.selection.highlight_selection()

        return proxy_index_list, view

    def search_replace(self):
        proxy_index_list, view = self.search()

        if proxy_index_list:
            view.undo_stack.push(
                self.replace_command(proxy_index_list[0])
                )

    def search_replace_all(self):
        proxy_index_list, view = self.search()
        undo_parent_cmd = None

        for index in proxy_index_list:
            if not view.model().flags(index) & Qt.ItemIsEditable:
                continue

            if not undo_parent_cmd:
                undo_parent_cmd = self.replace_command(index)
            else:
                self.replace_command(index, undo_parent_cmd)

        if proxy_index_list:
            view.undo_stack.push(undo_parent_cmd)

    def replace_command(self, index: QModelIndex, undo_parent: QUndoCommand=None):
        search_txt = self.edit_search.text()
        replace_txt = self.edit_replace.text()
        item_text = index.data(role=Qt.DisplayRole)
        new_text = item_text.replace(search_txt, replace_txt)

        return ItemEditUndoCommand(item_text, new_text, index, undo_parent, editing_done=False)
