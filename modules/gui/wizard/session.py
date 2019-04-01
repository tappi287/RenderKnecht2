from pathlib import Path

from PySide2.QtCore import QFile, QIODevice, QByteArray

from modules.globals import Resource
from modules.knecht_objects import KnData
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
    session_zip = CreateZip.settings_dir / 'LastPresetSession_data.zip'
    last_session_file = Path(settings_dir, 'last_preset_session.json')

    class SessionData:
        def __init__(self):
            self.pkg_filter = list()
            self.import_data = KnData()

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

    def load(self, file: Path=None):
        if not file:
            file = self.file
        self.data = Settings.pickle_load(self.data, file)

    def save(self, file: Path=None) -> bool:
        if not file:
            file = self.file

        return Settings.pickle_save(self.data, file)
