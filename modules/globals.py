import sys
import os
from pathlib import Path


UI_PATH = 'ui'
UI_PATHS_FILE = 'gui_resource_paths.json'

LOG_FILE_NAME = 'renderknecht2.log'
MAIN_LOGGER_NAME = 'knecht_main'
DEV_LOGGER_NAME = 'dev_module'
PLM_XML_NAMESPACE = '{http://www.plmxml.org/Schemas/PLMXMLSchema}'

SETTINGS_FILE = 'settings.json'
SETTINGS_DIR_NAME = 'RenderKnecht2'

DOCS_FILEPATH = 'locale/RenderKnecht2_Dokumentation.chm'
DOCS_HTML_FILEPATH = 'locale/help/RenderKnecht_Dokumentation.html'
DB_CONFIG_FILE = 'db_config.zip'

ITEM_WORK_INTERVAL = 90
ITEM_WORK_CHUNK = 8

UNDO_LIMIT = 50

# Updater Urls
# https://piwigo.ilikeviecher.com/ftp-upload/knecht2/version.txt
UPDATE_DIR_URL = 'https://piwigo.ilikeviecher.com/ftp-upload/knecht2/'
UPDATE_VERSION_FILE = 'version.txt'
UPDATE_INSTALL_FILE = 'RenderKnecht2_Setup_{version}_win64.exe'

# DeltaGen address
DG_TCP_IP = 'localhost'
DG_TCP_PORT = 3333

# KnechtViewer executable
KNECHT_VIEWER_BIN = 'KnechtViewer.exe'
POS_SCHNUFFI_BIN = 'PosSchnuffi.exe'

# Frozen or Debugger
if getattr(sys, 'frozen', False):
    # -- Running in PyInstaller Bundle ---
    FROZEN = True
else:
    # -- Running in IDE ---
    FROZEN = False


def get_current_modules_dir() -> str:
    """ Return path to this app modules directory """
    # Path to this module OR path to PyInstaller executable directory _MEIPASS
    mod_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__ + '/..')))

    return mod_dir


def get_settings_dir() -> str:
    _app_data = os.getenv('APPDATA')

    _knecht_settings_dir = os.path.join(_app_data, SETTINGS_DIR_NAME)

    if not os.path.exists(_knecht_settings_dir):
        try:
            os.mkdir(_knecht_settings_dir)
        except Exception as e:
            print('Error creating settings directory', e)
            return ''

    return _knecht_settings_dir


class SocketAddress:
    """ Pfad Aeffchen socket addresses """
    main = ('localhost', 9005)
    watcher = ('localhost', 9006)
    time_out = 20

    # Service broadcast
    service_magic = 'paln3s'
    service_port = 52121

    # List of valid IP subnet's
    valid_subnet_patterns = ['192.168.178', '192.168.13']


class Resource:
    """
        Qt resource paths for ui files and icons.
        Will be loaded from json dict on startup.

        create_gui_resource.py will create the json file for us.
        ui_path[filename] = relative path to ui file
        icon_path[filename] = Qt resource path
    """
    ui_paths = dict()
    icon_paths = dict()
    darkstyle = ":darkstyle/darkstyle.qss"
