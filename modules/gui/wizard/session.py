from pathlib import Path
from typing import List

from PySide2.QtCore import QFile, QIODevice, QByteArray

from modules.globals import Resource
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

    class _PresetPage(_DataParent):
        def __init__(self):
            super(WizardSession._PresetPage, self).__init__()

    class SessionData:
        def __init__(self):
            self.pkg_filter = list()
            self.import_data = KnData()
            # Model: List[FA_SIB_LUM_on]
            self.fakom_selection = dict()
            # PageId: PresetPage
            self.preset_pages = dict()

    class PkgDefaultFilter:
        package_filter = list()

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

    def load(self, file: Path=None):
        if not file:
            file = self.file
        self.data = Settings.pickle_load(self.data, file, compressed=True)

    def save(self, file: Path=None) -> bool:
        if not file:
            file = self.file

        self._clean_up_import_data()
        return Settings.pickle_save(self.data, file, compressed=True)
