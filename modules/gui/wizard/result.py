from PySide2.QtWidgets import QTabWidget, QTreeView, QWizardPage

from modules.globals import Resource
from modules.gui.gui_utils import SetupWidget, replace_widget
from modules.gui.ui_resource import IconRsc
from modules.gui.wizard.preset import PresetWizardPage
from modules.idgen import KnechtUuidGenerator as Kid
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


class ResultWizardPage(QWizardPage):
    def __init__(self, wizard):
        """ Wizard Result Page

        :param modules.gui.wizard.wizard.PresetWizard wizard: The parent wizard
        """
        super(ResultWizardPage, self).__init__()
        self.wizard = wizard
        self.session = wizard.session

        SetupWidget.from_ui_file(self, Resource.ui_paths['wizard_result'])

        self.setTitle(_('Wizard Ergebnis'))
        self.setSubTitle(_('Überblick über nicht verwendete Optionen und Pakete'))

        # -- Tabs --
        self.tabWidget: QTabWidget
        self.tabWidget.setTabText(0, _('Ergebnis'))
        self.tabWidget.setTabIcon(0, IconRsc.get_icon('options'))
        self.tabWidget.setTabText(1, _('Nicht verwendete Optionen'))
        self.tabWidget.setTabIcon(1, IconRsc.get_icon('delete_list'))

        # --- Tree Views ---
        self.unused_tree = self._init_tree_view(self.unused_tree)
        self.result_tree = self._init_tree_view(self.result_tree)

    def initializePage(self):
        self.collect_result()
        # self.collect_unused_options()
        LOGGER.info('Result Wizard Page initialized.')

    def cleanupPage(self):
        self.result_tree.clear_tree()
        self.unused_tree.clear_tree()

    def collect_result(self):
        kn_data = self.session.data.import_data
        kn_data.selected_models = list(self.session.data.fakom_selection.keys())

        converter = KnechtDataToModel(kn_data)
        trim_items = dict()

        # --- Create Trim Setups ---
        for model_code in kn_data.selected_models:
            trim = [t for t in kn_data.models if t.model == model_code]
            if not trim:
                continue
            trim = trim[0]
            trim_items[model_code] = dict()
            trim_item = converter.create_trim(trim)
            trim_item.refresh_id_data()
            trim_items[model_code]['trim_setup'] = trim_item
            trim_items[model_code]['trim_option'] = converter.create_trim_options(trim)
            trim_items[model_code]['packages'] = list()

        # --- Prepare presets ---
        preset_items = list()
        for page_id in self.session.data.preset_page_ids:
            preset_page: PresetWizardPage = self.wizard.page(page_id)
            if not isinstance(preset_page, PresetWizardPage):
                continue

            # -- Create Preset item
            preset_item = KnechtItem(None,
                                     ('000', preset_page.subTitle(), '', Kg.type_keys[Kg.preset], '', Kid.create_id())
                                     )
            trim_ref = trim_items[preset_page.model]['trim_setup'].copy(copy_children=False)
            trim_ref.convert_to_reference()
            preset_item.append_item_child(trim_ref)

            for _, pr_item in preset_page.preset_tree.editor.iterator.iterate_view():
                if pr_item.userType == Kg.variant:
                    # --- Add PR-option ---
                    preset_item.append_item_child(pr_item.copy())
                else:
                    # --- Add package reference ---
                    pkg_ref = pr_item.copy(copy_children=False)
                    pkg_ref.convert_to_reference()
                    preset_item.append_item_child(pkg_ref)
                    # --- Add package ---
                    trim_items[preset_page.model]['packages'].append(pr_item.copy())

            preset_items.append(preset_item)

        # --- Create trim items and packages ---
        root_item = KnechtItem()

        for model_code in kn_data.selected_models:
            # -- Add trim setup --
            trim_item = trim_items[model_code]['trim_setup']
            trim_item.setData(Kg.ORDER, f'{root_item.childCount():03d}')
            root_item.append_item_child(trim_item)

            # -- Add trim options --
            trim_options = trim_items[model_code]['trim_option']
            trim_options.setData(Kg.ORDER, f'{root_item.childCount():03d}')
            root_item.append_item_child(trim_options)

            # -- Add Packages --
            for pkg_item in trim_items[model_code]['packages']:
                pkg_item.setData(Kg.ORDER, f'{root_item.childCount():03d}')
                root_item.append_item_child(pkg_item)

        for preset_item in preset_items:
            preset_item.setData(Kg.ORDER, f'{root_item.childCount():03d}')
            root_item.append_item_child(preset_item)

        UpdateModel(self.result_tree).update(KnechtModel(root_item))
        self.result_tree.refresh()

    def collect_result_old(self):
        kn_data = self.session.data.import_data
        kn_data.selected_models = list(self.session.data.fakom_selection.keys())
        kn_data.read_trim, kn_data.read_options, kn_data.read_packages, kn_data.read_fakom = True, True, False, False

        # --- Create a Model with Trim Setups and Options ---
        converter = KnechtDataToModel(kn_data)
        UpdateModel(self.result_tree).update(
            KnechtModel(converter.create_root_item())
            )
        self.result_tree.refresh()
        self.result_tree.block_until_editor_finished()

        # --- Create pseudo FaKom Model and View ---
        kn_data.read_trim, kn_data.read_options, kn_data.read_packages, kn_data.read_fakom = False, False, False, True
        fakom_converter = KnechtDataToModel(kn_data)

        for model_code in self.session.data.fakom_selection.keys():
            trim = [t for t in kn_data.models if t.model == model_code]
            if not trim:
                continue
            else:
                trim = trim[0]

            fakom_converter.create_fakom(trim)

        # fakom_view = KnechtTreeView(None, None)
        UpdateModel(self.unused_tree).update(KnechtModel(fakom_converter.root_item))

        # -- Collect Trim Setups in dict by Model Code
        trim_items = {'model': 'TrimItem'}
        for _, item in self.result_tree.editor.iterator.iterate_view():
            value = item.data(Kg.VALUE)
            if value in self.session.data.fakom_selection.keys():
                if item.data(Kg.TYPE) == 'trim_setup':
                    trim_items[value] = item

        # --- Create Presets ---
        for page_id in self.session.data.preset_page_ids:
            preset_page: PresetWizardPage = self.wizard.page(page_id)
            if not isinstance(preset_page, PresetWizardPage):
                continue

            # -- Create Preset item
            preset_item = KnechtItem(None,
                                     ('000', preset_page.subTitle(), '', Kg.type_keys[Kg.preset], '', Kid.create_id())
                                     )
            self.result_tree.editor.create_top_level_rows([preset_item])
            preset_idx = self.result_tree.editor.match.index(preset_item.data(Kg.NAME), Kg.NAME)
            self.result_tree.editor.selection.clear_and_set_current(preset_idx)

            # -- Collect Preset Content
            pr_items = [pr_item.copy() for _, pr_item in preset_page.preset_tree.editor.iterator.iterate_view()]

            # -- Paste Preset Trim Reference
            self.wizard.automagic_clipboard.clear()
            self.wizard.automagic_clipboard.items = [trim_items[preset_page.model]] + pr_items
            self.wizard.automagic_clipboard.origin = self.result_tree
            self.result_tree.editor.paste_items(self.wizard.automagic_clipboard)
            self.result_tree.block_until_editor_finished()
            self.result_tree.model().sourceModel().validate_references()

    def collect_unused_options(self):
        # Add Unused Packages
        pkg_items = self._collect_unused_from_modeldict(self.session.pkg_models)
        pr_items = self._collect_unused_from_modeldict(self.session.opt_models)
        self.unused_tree.editor.create_top_level_rows(pkg_items + pr_items, at_row=0)

        # self.unused_tree.block_until_editor_finished()

    def _init_tree_view(self, tree_view: QTreeView) -> KnechtTreeView:
        """ Replace the UI Designer placeholder tree views """
        parent = tree_view.parent()
        new_view = KnechtTreeView(parent, None)
        replace_widget(tree_view, new_view)

        # Result wizard specific
        # new_view.setEditTriggers(QTreeView.NoEditTriggers)
        new_view.setDragDropMode(QTreeView.NoDragDrop)
        new_view.supports_drag_move = False
        new_view.supports_drop = False

        # Setup filter widget
        new_view.filter_text_widget = self.filter_edit
        # Setup keyboard shortcuts
        new_view.shortcuts = KnechtTreeViewShortcuts(new_view)

        # Update with placeholder Model to avoid access to unset attributes
        UpdateModel(new_view).update(KnechtModel())

        # for column in (Kg.VALUE, Kg.TYPE, Kg.REF, Kg.ID):
        #    new_view.hideColumn(column)

        return new_view

    def validatePage(self):
        return True

    @staticmethod
    def _collect_unused_from_modeldict(model_dict):
        unused_options = list()

        for model_code, item_model in model_dict.items():
            for item in item_model.root_item.iter_children():
                if not item.fixed_userType:  # Option is unlocked
                    unused_options.append(item.copy())

        LOGGER.debug('Collected %s unused options.', len(unused_options))
        return unused_options
