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
        new_view.setSelectionMode(QTreeView.MultiSelection)
        new_view.setSelectionBehavior(QTreeView.SelectRows)
        new_view.setEditTriggers(QTreeView.NoEditTriggers)
        new_view.setDragDropMode(QTreeView.NoDragDrop)
        new_view.setIndentation(15)

        # Setup filter widget
        new_view.filter_text_widget = self.filter_edit
        # Setup keyboard shortcuts
        new_view.shortcuts = KnechtTreeViewShortcuts(new_view)
        # new_view.context = ExcelContextMenu(self, new_view)

        # Update with placeholder Model to avoid access to unset attributes
        UpdateModel(new_view).update(KnechtModel())
        new_view.pressed.connect(self._fakom_item_pressed)

        return new_view

    @Slot(QModelIndex)
    def _fakom_item_pressed(self, index: QModelIndex):
        if not index.flags() & Qt.ItemIsSelectable:
            return

        # Reset saved selection
        self.wizard.session.data.fakom_selection = dict()

        # -- Populate Selection TreeWidget ---
        self.result_tree.clear()
        trim_items = dict()
        for prx_index in self.fakom_tree.selectionModel().selectedRows():
            trim_idx = self.get_index_group_parent(prx_index)
            trim_name = trim_idx.siblingAtColumn(Kg.NAME).data(Qt.DisplayRole)
            model = trim_idx.siblingAtColumn(Kg.VALUE).data(Qt.DisplayRole)
            item_name = f'{trim_name} {model}'

            if item_name not in trim_items:
                trim_item = QTreeWidgetItem(self.result_tree, [item_name])
                trim_item.setIcon(0, trim_idx.siblingAtColumn(Kg.style_column).data(Qt.DecorationRole) or QIcon())
                trim_item.setData(0, Qt.UserRole, trim_idx)
                trim_items[item_name] = trim_item
            else:
                trim_item = trim_items.get(item_name)

            name = prx_index.siblingAtColumn(Kg.NAME).data(Qt.DisplayRole)
            icon = prx_index.siblingAtColumn(Kg.style_column).data(Qt.DecorationRole) or QIcon()
            item = QTreeWidgetItem(trim_item, [name])
            item.setData(0, Qt.UserRole, prx_index)
            item.setIcon(0, icon)

            # -- Update Session selection data --
            self.wizard.session.data.fakom_selection.update(
                {model: (self.wizard.session.data.fakom_selection.get(model) or []) + [name]}
                )

        # -- Expand Results --
        for trim_item in trim_items.values():
            self.result_tree.expandItem(trim_item)

        self.completeChanged.emit()

    @Slot(QTreeWidgetItem, int)
    def _result_item_pressed(self, item: QTreeWidgetItem, column: int):
        if item.parent() is not self.result_tree:
            prx_index = item.data(0, Qt.UserRole)
            self.fakom_tree.scrollTo(prx_index, QAbstractItemView.PositionAtCenter)

    def load_fakom_selection(self):
        selection_dict = self.wizard.session.data.fakom_selection
        src_idx_selection_ls = list()
        view_iter = self.fakom_tree.editor.iterator

        for (idx, _) in view_iter.iterate_view():
            model = idx.siblingAtColumn(Kg.VALUE).data(Qt.DisplayRole)

            for (fa_idx, _) in view_iter.iterate_view(idx):
                for (sib_idx, _) in view_iter.iterate_view(fa_idx):
                    for (src_idx, _) in view_iter.iterate_view(sib_idx):
                        name = src_idx.siblingAtColumn(Kg.NAME).data(Qt.DisplayRole)

                        if name in (selection_dict.get(model) or []):
                            src_idx_selection_ls.append(src_idx)

        if src_idx_selection_ls:
            # Select saved selection
            self.fakom_tree.editor.selection.clear_and_select_src_index_ls(src_idx_selection_ls)

            # -- Trigger tree update
            prx_index = self.fakom_tree.model().mapFromSource(src_idx_selection_ls[0])
            self._fakom_item_pressed(prx_index)

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
