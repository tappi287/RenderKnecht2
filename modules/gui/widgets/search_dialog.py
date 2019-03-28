from PySide2.QtCore import Qt, QRect, QPoint, QModelIndex, QSortFilterProxyModel, QSize, QPropertyAnimation, \
    QEasingCurve, QAbstractAnimation
from PySide2.QtWidgets import QWidget, QPushButton, QComboBox, QLineEdit, QLabel, QDialog, QUndoCommand, QTreeView

from modules.itemview.item_edit_undo import ItemEditUndoCommand
from modules.itemview.model import KnechtModel, KnechtSortFilterProxyModel
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.globals import Resource
from modules.gui.gui_utils import SetupWidget, replace_widget
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
    last_view = None
    first_expand = True
    non_editable_columns = (Kg.ORDER, Kg.TYPE, Kg.REF, Kg.ID)
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

        self.size_anim = QPropertyAnimation(self, b'size')
        self.size_anim.setDuration(150)
        self.size_anim.setEasingCurve(QEasingCurve.OutCurve)

        # --- Init Tree View ---
        self.search_view = self._init_tree_view(self.search_view)

        # --- Collapse/Expand View ---
        self.search_view.minimumSizeHint = self._search_view_min_size_hint
        self.org_search_view_resize = self.search_view.resizeEvent
        self.search_view.resizeEvent = self._search_view_resize
        self.expand_btn.released.connect(self.expand_search_view)
        self.lbl_expand.setText(_('Ansicht'))

        self._reset_view()
        self.ui.tree_focus_changed.connect(self._ui_tree_focus_changed)

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
            if idx in self.non_editable_columns:
                continue
            self.column_box.addItem(c, userData=idx)

        self.column_box.setCurrentIndex(0)

    def center_on_ui(self):
        self.toggle_expand_search_view(immediate=True)

        r: QRect = self.ui.frameGeometry()
        width, height = self.default_width, self.size().height()
        center = QPoint(r.x() + r.width() / 2, r.y() + r.height() / 2)
        top_left = QPoint(center.x() - width / 2, center.y() - height / 2)
        self.setGeometry(QRect(top_left.x(), top_left.y(), width, height))

        self.first_expand = True

    def _search_view_min_size_hint(self):
        return QSize(self.search_view.sizeHint().width(), 0)

    def _search_view_resize(self, event):
        self.org_search_view_resize(event)

        if self.size_anim.state() != QAbstractAnimation.Running:
            if event.size().height() > 0:
                self.expand_btn.setChecked(True)
            else:
                self.expand_btn.setChecked(False)

        event.accept()

    def toggle_expand_search_view(self, immediate: bool=False):
        if self.expand_btn.isChecked():
            self.expand_btn.setChecked(False)
            self.expand_search_view(immediate=immediate)
        else:
            self.expand_btn.setChecked(True)
            self.expand_search_view(immediate=immediate)

    def expand_search_view(self, immediate: bool=False):
        if self.expand_btn.isChecked():
            height = self.search_view.size().height()
            if height < 250:
                height = 250
        else:
            height = 0

        self.search_view.resize(QSize(self.search_view.sizeHint().width(), height))
        self.size_anim.setStartValue(QSize(self.size().width(), self.size().height()))
        self.size_anim.setEndValue(QSize(self.size().width(), self.minimumSizeHint().height() + height))

        if immediate:
            self.resize(QSize(self.size().width(), self.minimumSizeHint().height() + height))
        else:
            self.size_anim.start()

    def _ui_tree_focus_changed(self, focus_view):
        if focus_view is self.search_view or focus_view is self.last_view:
            return
        self._reset_view()

    @staticmethod
    def _init_tree_view(tree_view: QTreeView) -> KnechtTreeView:
        """ Replace the UI Designer placeholder tree views """
        parent = tree_view.parent()
        new_view = KnechtTreeView(parent, None)
        replace_widget(tree_view, new_view)
        return new_view

    def _reset_view(self):
        UpdateModel(self.search_view).update(KnechtModel())

    def _update_document_view(self) -> KnechtTreeView:
        view = self.ui.tree_with_focus()
        self.last_view = view

        if view.model().sourceModel() != self.search_view.model().sourceModel():
            proxy_model = QSortFilterProxyModel()
            proxy_model.setFilterCaseSensitivity(Qt.CaseSensitive)
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
            # --- Update Search Tree View ---
            self.search_view.model().setFilterFixedString(txt)
            self.search_view.model().setFilterKeyColumn(column)
            src_index_ls = list()
            for index in proxy_index_list:
                src_index_ls.append(view.model().mapToSource(index))
            self.search_view.editor.selection.clear_and_select_src_index_ls(src_index_ls)
            setup_header_layout(self.search_view)

            # --- Update Actual Tree View ---
            view.setCurrentIndex(proxy_index_list[0])
            view.editor.selection.clear_and_select_proxy_index_ls(proxy_index_list)
            view.editor.selection.highlight_selection()
        else:
            self._reset_view()

        if self.first_expand:
            self.first_expand = False
            self.toggle_expand_search_view()

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
