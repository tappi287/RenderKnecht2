import re
from pathlib import Path

from PySide2.QtCore import QByteArray, QFile, QIODevice, QTimer

from modules.globals import Resource
from modules.gui.wizard.preset import PresetWizardPage
from modules.itemview.data_read import KnechtDataToModel
from modules.itemview.item import KnechtItem
from modules.itemview.model import KnechtModel
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.itemview.tree_view import KnechtTreeView
from modules.itemview.xml_read import KnechtOpenXml
from modules.itemview.xml_save import KnechtSaveXml
from modules.knecht_objects import KnData
from modules.knecht_utils import CreateZip
from modules.language import get_translation
from modules.log import init_logging
from modules.settings import Settings

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class WizardSession:
    settings_dir = CreateZip.settings_dir
    last_session_file = Path(settings_dir, 'last_preset_session.rksession')
    update_options_timer = QTimer()
    update_options_timer.setInterval(15)
    update_options_timer.setSingleShot(True)
    update_options_current_page = None

    class SessionData:
        def __init__(self):
            self.pkg_filter = list()
            self.pkg_filter_regex = str()
            self.import_data = KnData()
            self.fakom_selection = dict()  # str(Model): List[FA_SIB_LUM_on]
            self.preset_page_ids = set()   # Keep a set of created preset page id's
            self.preset_page_content = dict()  # Key: model_code+fakom Value: preset tree xml data as string

        def update_pkg_filter(self, pkg_filter_list):
            self.pkg_filter = pkg_filter_list
            self.pkg_filter_regex = str()

            for p in self.pkg_filter:
                self.pkg_filter_regex += p + '|'
            self.pkg_filter_regex = self.pkg_filter_regex[:-1]
            LOGGER.debug('Setup Package filter regex: %s', self.pkg_filter_regex)

        def store_preset_page_content(self, model_code: str, fakom: str, item_model: KnechtModel):
            xml_data, errors = KnechtSaveXml.save_xml('<not a file path>', item_model)

            if isinstance(xml_data, bytes):
                xml_data = xml_data.decode('UTF-8')
            elif isinstance(xml_data, bool):
                return

            LOGGER.debug('Saved Preset Page %s content with %s items', model_code + fakom,
                         item_model.root_item.childCount())
            self.preset_page_content[model_code + fakom] = xml_data

        def load_preset_page_content(self, model_code: str, fakom: str) -> KnechtModel:
            xml_data = self.preset_page_content.get(model_code + fakom)
            if not xml_data:
                return KnechtModel()

            root_item, error = KnechtOpenXml.read_xml(xml_data)
            LOGGER.debug('Loading Preset Page %s content with %s items', model_code + fakom, root_item.childCount())
            return KnechtModel(root_item)

    class PkgDefaultFilter:
        package_filter = list()

    default_session = SessionData()

    def __init__(self, wizard):
        """ Saves and loads all data to the wizard

        :param modules.gui.wizard.wizard.PresetWizard wizard:
        """
        self.wizard = wizard
        self.data = self.SessionData()

        self.update_options_timer.timeout.connect(self._update_available_options)

        # -- Preset Pages KnechtModels for available PR and Package options --
        self.opt_models = dict()  # ModelCode: KnechtModel
        self.pkg_models = dict()  # ModelCode: KnechtModel

        self._load_pkg_default_filter()

    def _load_pkg_default_filter(self):
        """ Read Package default filter from qt resources """
        f = QFile(Resource.icon_paths.get('pr_data'))

        try:
            f.open(QIODevice.ReadOnly)
            data: QByteArray = f.readAll()
            data: bytes = data.data()
            Settings.load_from_bytes(self.PkgDefaultFilter, data)
        except Exception as e:
            LOGGER.error(e)
        finally:
            f.close()

        self.data.pkg_filter = self.PkgDefaultFilter.package_filter[::]

        # Update Start Page Package Widget
        if hasattr(self.wizard, 'page_welcome'):
            self.wizard.page_welcome.reload_pkg_filter()

    def _clean_up_import_data(self):
        new_models = list()
        for trim in self.data.import_data.models:
            if trim.model in self.data.import_data.selected_models:
                new_models.append(trim)

        self.data.import_data.models = new_models

    def _load_default_attributes(self):
        """ Make sure that all attributes are present in SessionData after pickle load.
            Previous version may had less attributes.
        """
        for k in dir(self.default_session):
            v = getattr(self.default_session, k)
            if k.startswith('__') or not isinstance(v, (int, str, float, bool, list, dict, tuple)):
                continue

            # Set missing attributes
            if not hasattr(self.data, k):
                setattr(self.data, k, v)

    def reset_session(self):
        self.data = self.SessionData()
        self._load_pkg_default_filter()
        self.wizard.page_fakom.result_tree.clear()
        self.clear_preset_pages()

    def load(self, file: Path=None) -> bool:
        if not file:
            file = self.last_session_file

        try:
            self.data = Settings.pickle_load(self.data, file, compressed=True)
            self._load_default_attributes()
        except Exception as e:
            LOGGER.error('Error loading wizard session: %s', e)
            return False

        return True

    def save(self, file: Path=None) -> bool:
        if not file:
            file = self.last_session_file

        for page_id in self.data.preset_page_ids:
            page: PresetWizardPage = self.wizard.page(page_id)

            if not isinstance(page, PresetWizardPage):
                LOGGER.warning('Skipping non existing page %s', page_id)
                continue

            src_item_model = page.preset_tree.model().sourceModel()
            self.data.store_preset_page_content(page.model, page.fakom, src_item_model)

        self._clean_up_import_data()
        return Settings.pickle_save(self.data, file, compressed=True)

    def clear_preset_pages(self):
        page_id, cleared_pages = self.wizard.page_placeholder.id, 0

        if not page_id > 0:
            return

        while True:
            page_id += 1

            if isinstance(self.wizard.page(page_id), PresetWizardPage):
                self.wizard.removePage(page_id)
                cleared_pages += 1
            else:
                break

        LOGGER.debug('Cleared %s preset pages.', cleared_pages)

    def create_preset_pages(self):
        """ Create a Wizard preset page for each selected FaKom item """
        self.clear_preset_pages()
        self.data.preset_page_ids = set()

        for model_code, fakom_ls in self.data.fakom_selection.items():
            # Create available PR-Options and Packages per model
            self._update_preset_pages_item_models(model_code)

            for fakom in fakom_ls:
                preset_page = PresetWizardPage(self.wizard, model_code, fakom)
                page_id = self.wizard.addPage(preset_page)
                self.data.preset_page_ids.add(page_id)
                LOGGER.debug('Creating preset page: %s', page_id)

                # --- Load preset page content if available ---
                saved_model = self.data.load_preset_page_content(model_code, fakom)
                preset_page.load_model(saved_model)

        self.wizard.nav_menu.create_preset_page_entries()

    def update_available_options(self):
        self.update_options_timer.start()

    def _update_available_options(self):
        """ Update PR-Options and Packages Trees based on Preset Page Content """
        used_pr_families, used_pr_options, available_pr_families = set(), set(), set()
        visible_pkgs, used_pkgs = set(), set()

        current_page = self.wizard.page(self.wizard.currentId())
        if not isinstance(current_page, PresetWizardPage):
            return

        # -- Update currently used PR-Families on current page --
        used_pr_families = self._collect_tree_pr_data(current_page.preset_tree)[1]

        # --- Update PR-Options in use by all pages ---
        for page_id in self.data.preset_page_ids:
            preset_page: PresetWizardPage = self.wizard.page(page_id)
            pr_options = self._collect_tree_pr_data(preset_page.preset_tree)[0]
            used_pr_options.update(pr_options)

            for index, item in preset_page.preset_tree.editor.iterator.iterate_view():
                if item.data(Kg.TYPE) == 'package':
                    used_pkgs.add(item.data(Kg.VALUE))

        # --- Update available PR-Options ---
        for opt_index, opt_item in current_page.option_tree.editor.iterator.iterate_view():
            # Clear userType and locked style
            opt_item.fixed_userType = 0
            opt_item.style_unlocked()

            item_type = opt_item.data(Kg.TYPE)
            available_pr_families.add(item_type)

            if item_type in used_pr_families or opt_item.data(Kg.NAME) in used_pr_options:
                if current_page.option_lock_btn.isChecked():
                    opt_item.fixed_userType = Kg.group_item
                    opt_item.style_locked()
                else:
                    opt_item.style_italic()

        # --- Update available Packages ---
        for pkg_index, pkg_item in current_page.pkg_tree.editor.iterator.iterate_view():
            # Clear userType and locked style
            pkg_item.fixed_userType = 0
            pkg_item.style_unlocked()
            pkg_name = pkg_item.data(Kg.NAME)
            lock_pkg = False

            if pkg_item.data(Kg.VALUE) in used_pkgs:
                lock_pkg = True
            else:
                for pkg_variant in pkg_item.iter_children():
                    if pkg_variant.data(Kg.TYPE) in used_pr_families or pkg_name in used_pr_options:
                        lock_pkg = True
                        break

            # Package Country Filter
            if self.data.pkg_filter_regex and re.search(self.data.pkg_filter_regex, pkg_name):
                LOGGER.debug('Filtering Pkg: %s', pkg_name)
                lock_pkg = True

            if lock_pkg:
                if current_page.option_lock_btn.isChecked():
                    pkg_item.fixed_userType = Kg.group_item
                    pkg_item.style_locked()
                else:
                    pkg_item.style_italic()
            else:
                visible_pkgs.add(pkg_item.data(Kg.VALUE))

        # Show or Hide locked PR-Options and Packages
        if current_page.option_hide_btn.isChecked():
            current_page.option_tree.permanent_type_filter = list(available_pr_families.difference(used_pr_families))
            current_page.pkg_tree.permanent_type_filter = list(visible_pkgs)
        else:
            del current_page.option_tree.permanent_type_filter
            del current_page.pkg_tree.permanent_type_filter

    @staticmethod
    def _collect_tree_pr_data(view: KnechtTreeView):
        pr_options, pr_families = set(), set()

        for index, item in view.editor.iterator.iterate_view():
            variant_ls = view.editor.collect.collect_index(index)

            for variant in variant_ls.variants:
                pr_families.add(variant.item_type)
                pr_options.add(variant.name)

        return pr_options, pr_families

    def _update_preset_pages_item_models(self, model_code: str):
        """ Populate preset page models with available pr options and packages """
        if model_code not in self.opt_models:
            # --- Create Knecht item model for available PR-Options ---
            self.opt_models[model_code] = self._create_options_knecht_model(
                model_code, self.data.import_data, is_pr_options=True
                )
        if model_code not in self.pkg_models:
            # --- Create Knecht item model for available PR-Options ---
            self.pkg_models[model_code] = self._create_options_knecht_model(
                model_code, self.data.import_data, is_pr_options=False
                )

    @staticmethod
    def _create_options_knecht_model(model_code, import_data: KnData, is_pr_options=True):
        """ Create Knecht Item Model with either available PR-Options or Packages """
        converter = KnechtDataToModel(import_data)
        opt_item_model = KnechtModel()

        trim = [t for t in import_data.models if t.model == model_code]
        if not trim:
            return opt_item_model
        else:
            trim = trim[0]

        if is_pr_options:
            converter.create_pr_options(trim.iterate_optional_pr(), opt_item_model.root_item, ignore_pr_family=False)
        else:
            converter.create_packages(trim, opt_item_model.root_item, filter_pkg_by_pr_family=False)

        return opt_item_model
