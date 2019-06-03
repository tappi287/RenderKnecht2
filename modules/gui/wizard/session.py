from pathlib import Path
from typing import List, Dict

from PySide2.QtCore import QFile, QIODevice, QByteArray

from modules.globals import Resource
from modules.gui.wizard.preset import PresetWizardPage
from modules.itemview.data_read import KnechtDataToModel
from modules.itemview.model import KnechtModel
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.itemview.xml_read import KnechtOpenXml
from modules.itemview.xml_save import KnechtSaveXml
from modules.knecht_objects import KnData, _DataTrimOption, _DataParent, KnPr
from modules.knecht_utils import CreateZip
from modules.settings import Settings
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class WizardSession:
    settings_dir = CreateZip.settings_dir
    last_session_file = Path(settings_dir, 'last_preset_session.rksession')

    class SessionData:
        def __init__(self):
            self.pkg_filter = list()
            self.import_data = KnData()
            self.fakom_selection = dict()  # str(Model): List[FA_SIB_LUM_on]
            self.preset_page_content = dict()

        @staticmethod
        def store_preset_page_content(item_model: KnechtModel) -> str:
            xml_data, errors = KnechtSaveXml.save_xml('<not a file path>', item_model)

            if isinstance(xml_data, bytes):
                xml_data = xml_data.decode('UTF-8')
            elif isinstance(xml_data, bool):
                return ''
            LOGGER.debug('Saved Preset Page content with %s items', item_model.root_item.childCount())
            return xml_data

        def load_preset_page_content(self, page_id: int) -> KnechtModel:
            xml_data = self.preset_page_content.get(page_id)

            root_item, error = KnechtOpenXml.read_xml(xml_data)
            LOGGER.debug('Loading Preset Page content with %s items', root_item.childCount())
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

        # Convert Id keys to int
        self.data.preset_page_content = {int(k): v for k, v in self.data.preset_page_content.items()}

    def load(self, file: Path=None):
        if not file:
            file = self.last_session_file
        self.data = Settings.pickle_load(self.data, file, compressed=True)
        self._load_default_attributes()

    def save(self, file: Path=None) -> bool:
        if not file:
            file = self.last_session_file

        for page_id in self.data.preset_page_content.keys():
            page: PresetWizardPage = self.wizard.page(page_id)

            if not isinstance(page, PresetWizardPage):
                LOGGER.warning('Skipping invalid page %s', page_id)
                continue

            LOGGER.debug('Saving preset page: %s', page_id)
            src_item_model = page.preset_tree.model().sourceModel()
            self.data.preset_page_content[page_id] = self.data.store_preset_page_content(src_item_model)

        self._clean_up_import_data()
        return Settings.pickle_save(self.data, file, compressed=True)

    def create_preset_pages(self):
        for old_page_id in self.data.preset_page_content.keys():
            self.wizard.removePage(old_page_id)

        LOGGER.debug('Cleared %s preset pages.', len(self.data.preset_page_content.keys()))

        for model_code, fakom_ls in self.data.fakom_selection.items():
            # Create available PR-Options and Packages per model
            self._update_preset_pages_item_models(model_code)

            for fakom in fakom_ls:
                # TODO: First preset page content is not updated
                preset_page = PresetWizardPage(self.wizard, model_code, fakom)
                page_id = self.wizard.addPage(preset_page)

                # --- Load preset page content if available ---
                if page_id in self.data.preset_page_content:
                    LOGGER.debug('Loading preset page: %s', page_id)
                    saved_model = self.data.load_preset_page_content(page_id)
                    preset_page.load_model(saved_model)
                else:
                    self.data.preset_page_content[page_id] = None

        LOGGER.debug('Number of %s preset pages.', len(self.data.preset_page_content.keys()))

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
