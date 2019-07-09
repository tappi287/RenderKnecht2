import os
from pathlib import Path
from typing import Union

from PySide2 import QtWidgets

from modules.gui.widgets.path_util import path_exists
from modules.language import get_translation
from modules.log import init_logging
from modules.settings import KnechtSettings

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class FileDialog:
    """
        Shorthand class to create file dialogs. Dialog will block.
            file_key: see class attribute file_types
    """
    file_types = dict(
        xml=dict(title=_('Variants *.XML auswaehlen'), filter=_('Variant Preset Dateien (*.xml)')),
        xlsx=dict(title=_('Excel Dateien *.xlsx auswaehlen'), filter=_('Excel Dateien (*.xlsx)')),
        cmd=dict(title=_('Variants *.CMD auswaehlen'), filter=_('Variant CMD Dateien (*.cmd)')),
        pos=dict(title=_('DeltaGen POS Varianten *.xml oder *.pos auswaehlen'),
                 filter=_('DeltaGen POS Datei (*.xml;*.pos)')),
        rksession=dict(title=_('Session *.rksession auswaehlen'), filter=_('RK Session Dateien (*.rksession)')),
        dir=dict(title=_('Verzeichnis auswaehlen ...'), filter=None)
        )

    @classmethod
    def open(cls,
             parent=None, directory: Union[Path, str]=None, file_key: str= 'xml'
             ) -> Union[str, None]:
        return cls.open_existing_file(parent, directory, file_key)

    @classmethod
    def save(cls, parent, directory: Path, file_key: str='xml') -> Union[str, None]:
        return cls.__create_save_dialog(parent, cls.file_types[file_key]['title'],
                                        directory, cls.file_types[file_key]['filter'])

    @classmethod
    def open_dir(cls,
                 parent=None, directory: Union[Path, str] = None
                 ) -> Union[str, None]:
        return cls.open_existing_directory(parent, directory)

    @classmethod
    def open_existing_file(cls, parent=None,
                           directory: Union[Path, str]=None,
                           file_key: str= 'xml') -> Union[str, None]:
        # Update path
        directory = cls._get_current_path(directory)

        # Update filter and title depending on file type
        if file_key not in cls.file_types.keys():
            file_key = 'xml'

        title = cls.file_types[file_key]['title']
        file_filter = cls.file_types[file_key]['filter']

        file, file_ext = cls.__create_file_dialog(parent, title, directory, file_filter)

        if file and path_exists(file):
            if Path(file).suffix != f'.{file_key}':
                LOGGER.warning(f'User supposed to open: %s but opened: %s - returning None',
                               f'.{file_key}', Path(file).suffix)
                return

            KnechtSettings.app['current_path'] = Path(file).parent.as_posix()
            KnechtSettings.add_recent_file(Path(file).as_posix(), file_key)

        return file

    @classmethod
    def open_existing_directory(cls, parent=None, directory: Union[Path, str]=None,) -> Union[str, None]:
        # Update path
        directory = cls._get_current_path(directory)

        title = cls.file_types['dir']['title']

        directory = cls.__create_dir_dialog(parent, title, directory)

        if directory and path_exists(directory):
            KnechtSettings.app['current_path'] = Path(directory).as_posix()

        return directory

    # -------------------------------
    # ------- Dialog creation -------
    @staticmethod
    def __create_file_dialog(parent, title: str, directory: Path, file_filter: str) -> Union[str, None]:
        # Create and configure File Dialog
        dlg = QtWidgets.QFileDialog()
        dlg.setFileMode(QtWidgets.QFileDialog.ExistingFile)

        # This will block until the user has selected a file or canceled
        return dlg.getOpenFileName(parent, title, directory.as_posix(), file_filter)

    @staticmethod
    def __create_dir_dialog(parent, title: str, directory: Path) -> Union[str, None]:
        dlg = QtWidgets.QFileDialog()

        # This will block until the user has selected a directory or canceled
        return dlg.getExistingDirectory(parent, caption=title, directory=directory.as_posix())

    @staticmethod
    def __create_save_dialog(parent, title: str, directory: Path, file_filter: str) -> Union[str, None]:
        dlg = QtWidgets.QFileDialog()
        return dlg.getSaveFileName(parent, title, directory.as_posix(), file_filter)

    # -----------------------------------
    # ------- Path helper methods -------
    @staticmethod
    def _get_current_path(d) -> Path:
        # Current settings path
        __c = Path(KnechtSettings.app['current_path'])
        # Fallback path USERPROFILE path or current directory '.'
        __fallback = Path(os.getenv('USERPROFILE', '.'))

        if not d or not path_exists(d):
            if KnechtSettings.app['current_path'] not in ['', '.'] and path_exists(__c):
                # Set to settings current_path and continue with file vs. dir check
                d = __c
            else:
                return __fallback

        if Path(d).is_file():
            if path_exists(Path(d).parent):
                # Remove file and return directory
                return Path(d).parent
            else:
                return __fallback

        return Path(d)
