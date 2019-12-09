import re

from PySide2.QtCore import QModelIndex, QPoint, QRect, QSortFilterProxyModel, Qt, Slot, QRegularExpression
from PySide2.QtWidgets import QAbstractItemView, QCheckBox, QComboBox, QDialog, QLabel, QLineEdit, QPushButton, \
    QTreeView, QUndoCommand

from modules.globals import Resource
from modules.gui.gui_utils import SetupWidget, replace_widget
from modules.gui.widgets.expandable_widget import KnechtExpandableWidget
from modules.itemview.item_edit_undo import ItemEditUndoCommand
from modules.itemview.model import KnechtModel
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.itemview.model_update import UpdateModel
from modules.itemview.tree_view import KnechtTreeView
from modules.itemview.tree_view_utils import setup_header_layout
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class SearchDialog(QDialog):
    default_width = 800
    expand_height = 250
    last_view = None
    first_expand = True
    non_editable_columns = (Kg.ORDER, Kg.REF, Kg.ID)
    default_match_flags = Qt.MatchRecursive | Qt.MatchContains | Qt.MatchCaseSensitive
    view_filter_case_sensitivity = Qt.CaseSensitive

    def __init__(self, ui):
        """ Dialog to search and replace inside document views

        :param modules.gui.main_ui.KnechtWindow ui: Main Window
        """
        super(SearchDialog, self).__init__(ui)
        SetupWidget.from_ui_file(self, Resource.ui_paths['knecht_search'])
        self.ui = ui

        self.setWindowTitle(_('Suchen und Ersetzen'))
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        # --- Init Tree View ---
        self.search_view = self._init_tree_view(self.search_view)
        self._reset_view()
        self.ui.tree_focus_changed.connect(self._ui_tree_focus_changed)

        # --- Collapse/Expand View ---
        self.expand = KnechtExpandableWidget(self, self.expand_btn, self.search_view)

        self.lbl_expand.setText(_('Ansicht'))

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

        self.check_case: QCheckBox
        self.check_case.setText(_('Groß-/Kleinschreibung beachten'))
        self.check_case.toggled.connect(self.toggle_case_sensitivity)

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
            if idx in self.non_editable_columns:
                continue
            self.column_box.addItem(c, userData=idx)

        self.column_box.setCurrentIndex(0)

    def center_on_ui(self):
        self.expand.toggle_expand(immediate=True)

        r: QRect = self.ui.frameGeometry()
        width, height = self.default_width, self.size().height()
        center = QPoint(r.x() + r.width() / 2, r.y() + r.height() / 2)
        top_left = QPoint(center.x() - width / 2, center.y() - height / 2)
        self.setGeometry(QRect(top_left.x(), top_left.y(), width, height))

        self.first_expand = True

    @Slot(bool)
    def toggle_case_sensitivity(self, checked: bool):
        if checked:
            self.default_match_flags = Qt.MatchRecursive | Qt.MatchContains | Qt.MatchCaseSensitive
            self.view_filter_case_sensitivity = Qt.CaseSensitive
        else:
            self.default_match_flags = Qt.MatchRecursive | Qt.MatchContains
            self.view_filter_case_sensitivity = Qt.CaseInsensitive

        self.search_view.model().setFilterCaseSensitivity(self.view_filter_case_sensitivity)

    def _ui_tree_focus_changed(self, focus_view):
        if focus_view is self.search_view or focus_view is self.last_view:
            return
        self._reset_view()

    def _init_tree_view(self, tree_view: QTreeView) -> KnechtTreeView:
        """ Replace the UI Designer placeholder tree views """
        parent = tree_view.parent()
        new_view = KnechtTreeView(parent, None)
        replace_widget(tree_view, new_view)

        new_view.pressed.connect(self._view_item_pressed)

        return new_view

    @Slot(QModelIndex)
    def _view_item_pressed(self, index: QModelIndex):
        if not self.last_view:
            return
        LOGGER.debug(index.data(Qt.DisplayRole))

        src_index = self.search_view.model().mapToSource(index)
        proxy_index = self.last_view.model().mapFromSource(src_index)
        self.last_view.scrollTo(proxy_index, QAbstractItemView.PositionAtCenter)

    def _last_view_deleted(self, obj=None):
        LOGGER.debug('Clearing deleted last view %s', obj)
        self.last_view = None

    def _reset_view(self):
        UpdateModel(self.search_view).update(KnechtModel())

    def _update_search_view(self, view, proxy_index_list, txt, column):
        """ Mirror search results in search tree view """
        self.search_view.model().setFilterFixedString(txt)
        self.search_view.model().setFilterKeyColumn(column)

        src_index_ls = list()
        for index in proxy_index_list:
            src_index_ls.append(view.model().mapToSource(index))

        self.search_view.editor.selection.clear_and_select_src_index_ls(src_index_ls)
        setup_header_layout(self.search_view)

    def _update_document_view(self) -> KnechtTreeView:
        """ Update current view to search in and update search tree view accordingly """
        view = self.ui.tree_with_focus()
        self.last_view = view
        self.last_view.destroyed.connect(self._last_view_deleted)

        if view.model().sourceModel() != self.search_view.model().sourceModel():
            proxy_model = QSortFilterProxyModel()
            proxy_model.setFilterCaseSensitivity(self.view_filter_case_sensitivity)
            proxy_model.setSourceModel(view.model().sourceModel())
            proxy_model.setRecursiveFilteringEnabled(True)
            self.search_view.setModel(proxy_model)

            for c in (Kg.REF, Kg.ID):
                self.search_view.hideColumn(c)

            LOGGER.debug('Search Dialog Document View updated.')

        return view

    def search(self):
        txt = self.edit_search.text()
        column = self.column_box.currentData()

        view = self._update_document_view()

        # --- Skip empty searches ---
        if not txt:
            return list(), view

        proxy_index_list = view.editor.match.indices(txt, column, match_flags=self.default_match_flags)

        if proxy_index_list:
            self._update_search_view(view, proxy_index_list, txt, column)

            # --- Update Actual Tree View ---
            view.setCurrentIndex(proxy_index_list[0])
            view.editor.selection.clear_and_select_proxy_index_ls(proxy_index_list)
            view.editor.selection.highlight_selection()
        else:
            self._reset_view()

        if self.first_expand:
            self.first_expand = False
            if not self.expand_btn.isChecked():
                self.expand.toggle_expand()

        return proxy_index_list, view

    def search_replace(self):
        proxy_index_list, view = self.search()
        if not proxy_index_list:
            return

        first_index = proxy_index_list[0]

        if first_index and first_index.flags() & Qt.ItemIsEditable:
            view.undo_stack.push(self.replace_command(first_index))

    def search_replace_all(self):
        proxy_index_list, view = self.search()
        undo_parent_cmd = None

        for index in proxy_index_list:
            if not index.flags() & Qt.ItemIsEditable:
                continue

            if not undo_parent_cmd:
                undo_parent_cmd = self.replace_command(index)
            else:
                self.replace_command(index, undo_parent_cmd)

        if undo_parent_cmd:
            view.undo_stack.push(undo_parent_cmd)

    def replace_command(self, index: QModelIndex, undo_parent: QUndoCommand=None):
        search_txt = self.edit_search.text()
        replace_txt = self.edit_replace.text()
        item_text = index.data(role=Qt.DisplayRole)

        if self.check_case.isChecked():
            flags = 0
        else:
            flags = re.IGNORECASE

        try:
            new_text = re.sub(QRegularExpression.escape(search_txt), replace_txt, item_text, flags=flags)
        except Exception as e:
            LOGGER.error(e)
            return

        if new_text == item_text:
            return

        return ItemEditUndoCommand(item_text, new_text, index, undo_parent, editing_done=False)
