from pathlib import Path
from typing import List

from PySide2.QtWidgets import QTabWidget, QTreeView, QWizardPage

from modules.globals import Resource
from modules.gui.gui_utils import SetupWidget, replace_widget
from modules.gui.ui_resource import IconRsc
from modules.gui.wizard.preset import PresetWizardPage, PresetTreeViewShortcutOverrides
from modules.idgen import KnechtUuidGenerator as Kid
from modules.itemview.data_read import KnechtDataToModel
from modules.itemview.item import KnechtItem
from modules.itemview.model import KnechtModel
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.itemview.model_update import UpdateModel
from modules.itemview.tree_view import KnechtTreeView
from modules.itemview.tree_view_utils import KnechtTreeViewShortcuts
from modules.knecht_objects import KnPr, KnTrim
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
        self.wizard.save_last_session()

        self.collect_result()
        self.collect_unused_options()
        LOGGER.info('Result Wizard Page initialized.')

    def cleanupPage(self):
        self.result_tree.clear_tree()
        self.unused_tree.clear_tree()

    @staticmethod
    def _get_pr_from_list(pr_list: List[KnPr], pr_name: str) -> KnPr:
        match = KnPr()
        for pr in pr_list:
            if pr.name == pr_name:
                match = pr
                break
        return match

    @staticmethod
    def _get_trim_from_models(models, model_code) -> KnTrim:
        matched_trim = KnTrim()
        for trim in models:
            if trim.model == model_code:
                matched_trim = trim
                break
        return matched_trim

    def collect_result(self):
        kn_data = self.session.data.import_data
        converter = KnechtDataToModel(kn_data)
        trim_items = dict()

        # --- Create Trim Setups ---
        for model_code in self.session.data.fakom_selection.keys():
            trim = self._get_trim_from_models(kn_data.models, model_code)
            trim_items[model_code] = dict()
            trim_item = converter.create_trim(trim)
            trim_item.refresh_id_data()
            trim_items[model_code]['trim_setup'] = trim_item
            trim_items[model_code]['trim_option'] = converter.create_trim_options(trim)
            trim_items[model_code]['packages'] = list()
            trim_items[model_code]['fakom'] = dict()

        # -- Create FaKom Items --
        for preset_page in self.session.iterate_preset_pages():
            fakom_ls = preset_page.fakom.split('-')
            if len(fakom_ls) < 4:
                continue
            trim = self._get_trim_from_models(kn_data.models, preset_page.model)

            # Create lists of List[KnPr] for SIB/VOS/LUM families
            sib_pr_ls = [pr for pr in trim.iterate_available_pr() if pr.family.casefold() == 'sib']
            lum_pr_ls = [pr for pr in trim.iterate_available_pr() if pr.family.casefold() == 'lum']
            vos_pr_ls = [pr for pr in trim.iterate_available_pr() if pr.family.casefold() == 'vos']

            fa, sib, vos, lum = fakom_ls
            LOGGER.debug('Creating Fakom Item %s %s %s %s', fa, sib, vos, lum)
            sib_pr = self._get_pr_from_list(sib_pr_ls, sib)
            vos_pr = self._get_pr_from_list(vos_pr_ls, vos)
            lum_pr = self._get_pr_from_list(lum_pr_ls, lum)

            fakom_type = 'fakom_option'
            if not {sib_pr.value, vos_pr.value, lum_pr.value}.difference('L'):
                fakom_type = 'fakom_setup'

            fa_item = converter.create_fakom_item(
                None, trim.model, trim.model_text, fa, sib, vos, lum,
                sib_pr.desc, vos_pr.desc, lum_pr.desc, fakom_type, False
                )
            fa_item.refresh_id_data()
            trim_items[preset_page.model]['fakom'][preset_page.fakom] = fa_item

        # --- Prepare presets ---
        preset_items = list()
        for preset_page in self.session.iterate_preset_pages():
            # -- Create Preset item --
            preset_item = KnechtItem(None,
                                     ('000', preset_page.subTitle(), '', Kg.type_keys[Kg.preset], '', Kid.create_id())
                                     )
            # -- Add reference to trim setup --
            trim_ref = trim_items[preset_page.model]['trim_setup'].copy(copy_children=False)
            trim_ref.convert_to_reference()
            preset_item.append_item_child(trim_ref)

            # -- Add reference to fakom item --
            fa_ref = trim_items[preset_page.model]['fakom'][preset_page.fakom].copy(copy_children=False)
            fa_ref.convert_to_reference()
            preset_item.append_item_child(fa_ref)

            # -- Collect preset content --
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

        # --- Create trim, package and fakom items ---
        root_item = KnechtItem()

        for model_code in self.session.data.fakom_selection.keys():
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

            # -- Add FaKom Items --
            for fa_item in trim_items[model_code]['fakom'].values():
                fa_item.setData(Kg.ORDER, f'{root_item.childCount():03d}')
                root_item.append_item_child(fa_item)

            # -- Add separator --
            root_item.append_item_child(
                KnechtItem(None, (f'{root_item.childCount():03d}', '', '', 'separator'))
                )

        for preset_item in preset_items:
            preset_item.setData(Kg.ORDER, f'{root_item.childCount():03d}')
            root_item.append_item_child(preset_item)

        UpdateModel(self.result_tree).update(KnechtModel(root_item))

    def collect_unused_options(self):
        # Add Unused Packages
        pkg_items = self._collect_unused_from_modeldict(self.session.pkg_models)
        pr_items = self._collect_unused_from_modeldict(self.session.opt_models)
        self.unused_tree.editor.create_top_level_rows(pkg_items + pr_items, at_row=0)

    def _init_tree_view(self, tree_view: QTreeView) -> KnechtTreeView:
        """ Replace the UI Designer placeholder tree views """
        parent = tree_view.parent()
        new_view = KnechtTreeView(parent, None)
        replace_widget(tree_view, new_view)

        # Result wizard specific
        new_view.setEditTriggers(QTreeView.NoEditTriggers)
        new_view.setDragDropMode(QTreeView.NoDragDrop)
        new_view.supports_drag_move = False
        new_view.supports_drop = False

        # Setup filter widget
        new_view.filter_text_widget = self.filter_edit
        # Setup keyboard shortcuts
        new_view.shortcuts = KnechtTreeViewShortcuts(new_view)
        # Override Edit Shotcuts
        new_view.shortcut_overrides = PresetTreeViewShortcutOverrides(new_view)

        # Update with placeholder Model to avoid access to unset attributes
        UpdateModel(new_view).update(KnechtModel())

        for column in (Kg.VALUE, Kg.TYPE, Kg.REF, Kg.ID):
            new_view.hideColumn(column)

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