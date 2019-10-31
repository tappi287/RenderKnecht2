from PySide2.QtCore import QModelIndex, Qt, Slot, QTimer
from PySide2.QtGui import QIcon
from PySide2.QtWidgets import QAbstractItemView, QTreeView, QTreeWidget, QTreeWidgetItem, QWizardPage

from modules.globals import Resource
from modules.gui.gui_utils import SetupWidget, replace_widget
from modules.gui.ui_resource import IconRsc
from modules.itemview.data_read import KnechtDataToModel
from modules.itemview.item import KnechtItem
from modules.itemview.model import KnechtModel
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.itemview.model_update import UpdateModel
from modules.itemview.tree_view import KnechtTreeView
from modules.itemview.tree_view_utils import KnechtTreeViewShortcuts
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class FakomWizardPage(QWizardPage):
    no_data = _('Keine Daten vorhanden.')

    def __init__(self, wizard):
        """ Wizard Page to select FaKom Items

        :param modules.gui.wizard.wizard.PresetWizard wizard: The parent wizard
        """
        super(FakomWizardPage, self).__init__()
        self.wizard = wizard
        SetupWidget.from_ui_file(self, Resource.ui_paths['wizard_fakom'])

        self.setTitle(_('Preset Selection'))
        self.setSubTitle(_('Farbkombinationen auswählen aus denen Presets erstellt werden sollen.'))

        # -- Setup Page Ui --
        self.selection_icon.setPixmap(IconRsc.get_pixmap('fakom_trim'))
        self.selection_label.setText(_('Ausgewählte Presets'))

        # --- Tree Views ---
        self.fakom_tree = self._init_tree_view(self.fakom_tree)
        self.result_tree: QTreeWidget
        self.result_tree.itemPressed.connect(self._result_item_pressed)

    def initializePage(self):
        data = self.wizard.session.data.import_data
        item_creator = KnechtDataToModel(data)

        # -- Populate Preset Tree --
        for trim in data.models:
            if trim.model not in data.selected_models:
                continue

            item_data = (f'{item_creator.root_item.childCount():03d}', trim.model_text, trim.model, 'trim_setup')
            trim_item = KnechtItem(item_creator.root_item, item_data)
            trim_item.fixed_userType = Kg.group_item
            item_creator.create_fakom(trim, is_preset_wizard=True, parent_item=trim_item)
            item_creator.root_item.append_item_child(trim_item)

        fakom_model = KnechtModel(item_creator.root_item)
        for column in (Kg.VALUE, Kg.DESC, Kg.TYPE, Kg.REF, Kg.ID):
            self.fakom_tree.hideColumn(column)
        UpdateModel(self.fakom_tree).update(fakom_model)

        QTimer.singleShot(50, self.load_fakom_selection)

        LOGGER.info('FaKom Wizard Page initialized.')

    def _init_tree_view(self, tree_view: QTreeView) -> KnechtTreeView:
        """ Replace the UI Designer placeholder tree views """
        parent = tree_view.parent()
        new_view = KnechtTreeView(parent, None)
        replace_widget(tree_view, new_view)

        # Fakom wizard specific
        new_view.setSelectionMode(QTreeView.NoSelection)
        new_view.setSelectionBehavior(QTreeView.SelectRows)
        new_view.setEditTriggers(QTreeView.NoEditTriggers)
        new_view.setDragDropMode(QTreeView.NoDragDrop)
        new_view.supports_drag_move = False
        new_view.setIndentation(15)

        # Setup filter widget
        new_view.filter_text_widget = self.filter_edit
        # Setup keyboard shortcuts
        new_view.shortcuts = KnechtTreeViewShortcuts(new_view)

        # Update with placeholder Model to avoid access to unset attributes
        UpdateModel(new_view).update(KnechtModel())
        new_view.clicked.connect(self._fakom_item_pressed)

        return new_view

    @Slot(QModelIndex)
    def _fakom_item_pressed(self, prx_index: QModelIndex):
        if not prx_index.flags() & Qt.ItemIsSelectable:
            return

        self.fakom_tree.model().clear_filter()
        already_selected = False

        current_fa_name = prx_index.siblingAtColumn(Kg.NAME).data(Qt.DisplayRole)
        current_trim_idx = self.get_index_group_parent(prx_index)
        current_model_code = current_trim_idx.siblingAtColumn(Kg.VALUE).data(Qt.DisplayRole)

        # -- Lookup if index is already selected
        for model_code, fa_name_ls in self.wizard.session.data.fakom_selection.items():
            if current_model_code == model_code:
                if current_fa_name in fa_name_ls:
                    already_selected = True

        if already_selected:
            # Remove entry
            self.wizard.session.data.fakom_selection[current_model_code].remove(current_fa_name)
            if not self.wizard.session.data.fakom_selection[current_model_code]:
                self.wizard.session.data.fakom_selection.pop(current_model_code)
        else:
            # Add entry
            self.wizard.session.data.fakom_selection.update(
                {current_model_code:
                 (self.wizard.session.data.fakom_selection.get(current_model_code) or []) + [current_fa_name]
                 }
                )

        # -- Style selected items with checkmark
        src_idx_selection_ls = list()
        for model_code, fa_src_idx, fa_item in self.iter_all_fakom_items():
            if fa_src_idx.data(Qt.DisplayRole) in (self.wizard.session.data.fakom_selection.get(model_code) or []):
                self._style_index_checked(fa_src_idx)
                src_idx_selection_ls.append(fa_src_idx)
            else:
                if fa_src_idx.data(Qt.DecorationRole):
                    self.fakom_tree.model().sourceModel().setData(fa_src_idx, QIcon(), Qt.DecorationRole)

        self.fakom_tree.model().apply_last_filter()

        # Empty selection
        if not src_idx_selection_ls:
            self.wizard.session.data.fakom_selection = dict()
            self.completeChanged.emit()
            self.result_tree.clear()
            return

        self.populate_result_tree(src_idx_selection_ls)

        self.completeChanged.emit()

    def _style_index_checked(self, src_idx: QModelIndex):
        self.fakom_tree.model().sourceModel().setData(src_idx, IconRsc.get_icon('checkmark'), Qt.DecorationRole)

    def populate_result_tree(self, src_idx_selection_ls):
        self.result_tree.clear()

        # -- Populate Selection TreeWidget ---
        trim_items = dict()
        for model_code in self.wizard.session.data.fakom_selection.keys():
            trim = [t for t in self.wizard.session.data.import_data.models if t.model == model_code][0]
            trim_item_name = f'{trim.model_text} {model_code}'
            trim_item = QTreeWidgetItem([trim_item_name])
            trim_item.setIcon(0, IconRsc.get_icon('car'))
            trim_items[trim_item_name] = trim_item

        for src_index in src_idx_selection_ls:
            trim_idx = self.get_index_group_parent(src_index)
            model = trim_idx.siblingAtColumn(Kg.VALUE).data(Qt.DisplayRole)
            trim_item_name = f'{trim_idx.siblingAtColumn(Kg.NAME).data(Qt.DisplayRole)} {model}'

            trim_item = trim_items.get(trim_item_name)
            trim_item.setData(0, Qt.UserRole, trim_idx)

            name = src_index.siblingAtColumn(Kg.NAME).data(Qt.DisplayRole)
            icon = src_index.siblingAtColumn(Kg.style_column).data(Qt.DecorationRole) or QIcon()
            item = QTreeWidgetItem(trim_item, [name])
            item.setData(0, Qt.UserRole, src_index)
            item.setIcon(0, icon)

        # -- Expand DeltaGenResult Tree --
        for trim_item in trim_items.values():
            self.result_tree.addTopLevelItem(trim_item)
            self.result_tree.expandItem(trim_item)

    def iter_all_fakom_items(self):
        def _iter_fakom_view(parent: QModelIndex = QModelIndex()):
            return self.fakom_tree.editor.iterator.iterate_view(parent, Kg.NAME)

        for m_idx, _ in _iter_fakom_view():
            model_code = m_idx.siblingAtColumn(Kg.VALUE).data(Qt.DisplayRole)

            for b, _ in _iter_fakom_view(m_idx):
                for c, _ in _iter_fakom_view(b):
                    for fa_idx, fa_item in _iter_fakom_view(c):
                        yield model_code, fa_idx, fa_item

    @Slot(QTreeWidgetItem, int)
    def _result_item_pressed(self, item: QTreeWidgetItem, column: int):
        if item.parent() is not self.result_tree:
            prx_index = self.fakom_tree.model().mapFromSource(item.data(0, Qt.UserRole))
            if prx_index.isValid():
                self.fakom_tree.scrollTo(prx_index, QAbstractItemView.PositionAtCenter)

    def load_fakom_selection(self):
        selection_dict = self.wizard.session.data.fakom_selection
        src_idx_selection_ls = list()

        for model_code, fa_src_idx, _ in self.iter_all_fakom_items():
            if fa_src_idx.data(Qt.DisplayRole) in (selection_dict.get(model_code) or []):
                self._style_index_checked(fa_src_idx)
                src_idx_selection_ls.append(fa_src_idx)

        if src_idx_selection_ls:
            # Select saved selection
            self.fakom_tree.editor.selection.clear_and_select_src_index_ls(src_idx_selection_ls)
            self.fakom_tree.editor.selection.clear_selection()

            # -- Trigger tree update
            self.populate_result_tree(src_idx_selection_ls)

        self.completeChanged.emit()

    @staticmethod
    def get_index_group_parent(prx_index: QModelIndex) -> QModelIndex:
        """ Get the highest valid parent index """
        parent_idx = prx_index.parent()

        while parent_idx.parent().isValid():
            parent_idx = parent_idx.parent()

        return parent_idx

    def validatePage(self):
        self.wizard.session.create_preset_pages()
        return True

    def isComplete(self):
        if self.wizard.session.data.fakom_selection:
            return True
        return False
