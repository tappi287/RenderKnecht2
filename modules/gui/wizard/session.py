from pathlib import Path
from typing import List

from PySide2.QtCore import QFile, QIODevice, QByteArray

from modules.globals import Resource
from modules.gui.wizard.preset import PresetWizardPage
from modules.itemview.model import KnechtModel
from modules.knecht_objects import KnData, _DataTrimOption, _DataParent
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
            # PageId: PresetPage.preset_tree's KnechtModel
            self.preset_page_models = dict()
            # ModelCode: List[KnPr]
            self.used_options = dict()
            # ModelCode: List[KnPackage]
            self.used_packages = dict()

    class PkgDefaultFilter:
        package_filter = list()

    default_session = SessionData()

    def __init__(self, file: Path=None):
        self.file = file

        if not file:
            self.file = self.last_session_file

        self.data = self.SessionData()
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

    def load_preset_page_options(self, page_id: int, model_code: str, preset_page: PresetWizardPage):
        self.data.preset_page_models[page_id] = KnechtModel()
        preset_page.setup_preset_tree_model(page_id)

        if model_code not in self.data.used_options:
            self.data.used_options[model_code] = list()
        if model_code not in self.data.used_packages:
            self.data.used_packages[model_code] = list()
