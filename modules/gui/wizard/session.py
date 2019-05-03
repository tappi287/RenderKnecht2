from pathlib import Path
from typing import List, Dict

from PySide2.QtCore import QFile, QIODevice, QByteArray

from modules.globals import Resource
from modules.gui.wizard.preset import PresetWizardPage
from modules.itemview.data_read import KnechtDataToModel
from modules.itemview.model import KnechtModel
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
            # Model: List[FA_SIB_LUM_on]
            self.fakom_selection = dict()

    class PkgDefaultFilter:
        package_filter = list()

    default_session = SessionData()

    def __init__(self, file: Path=None):
        self.file = file

        if not file:
            self.file = self.last_session_file

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

    def load(self, file: Path=None):
        if not file:
            file = self.file
        self.data = Settings.pickle_load(self.data, file, compressed=True)
        self._load_default_attributes()

    def save(self, file: Path=None) -> bool:
        if not file:
            file = self.file

        self._clean_up_import_data()
        return Settings.pickle_save(self.data, file, compressed=True)

    def prepare_preset_page_content(self, model_code: str):
        self._update_preset_pages_item_models(model_code)

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
        converter = KnechtDataToModel(KnData())
        opt_item_model = KnechtModel()

        trim = [t for t in import_data.models if t.model == model_code]
        if not trim:
            return opt_item_model
        else:
            trim = trim[0]

        if is_pr_options:
            converter.create_pr_options(trim.iterate_optional_pr(), opt_item_model.root_item, ignore_pr_family=True)
        else:
            converter.create_packages(trim, opt_item_model.root_item, filter_pkg_by_pr_family=False)

        return opt_item_model
