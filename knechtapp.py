import logging
import sys
import multiprocessing
from multiprocessing import Queue

from PySide2.QtCore import Qt
from PySide2.QtWidgets import QApplication

from modules.globals import FROZEN, MAIN_LOGGER_NAME
from modules.gui.gui_utils import KnechtExceptionHook
from modules.gui.main_app import KnechtApp
from modules.log import init_logging, setup_log_queue_listener, setup_logging
from modules.settings import KnechtSettings, delayed_log_setup
from ui import darkstyle, gui_resource

if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    print('Using high dpi Pixmaps')

VERSION = '0.989'
"""
 BUG
$ ./RenderKnecht.exe
libpng warning: iCCP: known incorrect sRGB profile
Free Image Libary: E:/PycharmProjects/RenderKnecht2/dist/RenderKnecht2/bin/freei                                                                                                                                             mage-3.15.1-win64.dll
Application language loaded from settings:  de
KnechtSettings successfully loaded from file.
Settings loaded from file.
Using high dpi Pixmaps
Logging setup called:  knechtapp.py main
Logger requested by:  knechtapp.py initialize_log_listener INFO
Removing handler that will be added to queue listener:  <RotatingFileHandler C:\                                                                                                                                             Users\CADuser\AppData\Roaming\RenderKnecht2\renderknecht2.log (INFO)>
Removing handler that will be added to queue listener:  <NullHandler (INFO)>
Removing handler that will be added to queue listener:  <StreamHandler <stdout>                                                                                                                                              (INFO)>
Logger requested by:  settings.py delayed_log_setup INFO
08.07.2019 17:56 gui.ui_overlay ERROR: Overlay Parent has no attribute "header".                                                                                                                                              Using frame height.
08.07.2019 17:56 gui.ui_overlay ERROR: Overlay parent has no horizontal scrollba                                                                                                                                             r. 'PySide2.QtWidgets.QWidget' object has no attribute 'horizontalScrollBar'
08.07.2019 17:56 gui.ui_overlay INFO: Overlay widget has no scroll bar or header                                                                                                                                             : 'PySide2.QtWidgets.QWidget' object has no attribute 'header'
08.07.2019 17:56 gui.gui_utils CRITICAL:   File "knechtapp.py", line 107, in <mo                                                                                                                                             dule>
  File "knechtapp.py", line 84, in main
  File "modules\gui\main_app.py", line 62, in __init__
  File "modules\gui\main_ui.py", line 100, in __init__
  File "modules\gui\widgets\main_ui_widgets.py", line 91, in __init__
  File "modules\gui\widgets\path_util.py", line 119, in set_path
  File "pathlib.py", line 1329, in exists
  File "pathlib.py", line 1151, in stat

08.07.2019 17:56 gui.gui_utils CRITICAL: <class 'OSError'>: [WinError 1326] Der                                                                                                                                              Benutzername oder das Kennwort ist falsch: 'x:\\datapool\\Q7\\SQ7\\OPT_SQ7_2020_                                                                                                                                             Stossfaenger-Kontrastlackierung-Scandiumgrau_2K9\\Arbeitsmaterial'
[10356] Failed to execute script knechtapp
Traceback (most recent call last):
  File "knechtapp.py", line 107, in <module>
  File "knechtapp.py", line 84, in main
  File "modules\gui\main_app.py", line 62, in __init__
  File "modules\gui\main_ui.py", line 100, in __init__
  File "modules\gui\widgets\main_ui_widgets.py", line 91, in __init__
  File "modules\gui\widgets\path_util.py", line 119, in set_path
  File "pathlib.py", line 1329, in exists
  File "pathlib.py", line 1151, in stat
OSError: [WinError 1326] Der Benutzername oder das Kennwort ist falsch: 'x:\\dat                                                                                                                                             apool\\Q7\\SQ7\\OPT_SQ7_2020_Stossfaenger-Kontrastlackierung-Scandiumgrau_2K9\\A                                                                                                                                             rbeitsmaterial'
Exception in thread Thread-1:
Traceback (most recent call last):
  File "multiprocessing\connection.py", line 312, in _recv_bytes
BrokenPipeError: [WinError 109] Die Pipe wurde beendet

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "threading.py", line 917, in _bootstrap_inner
  File "threading.py", line 865, in run
  File "logging\handlers.py", line 1475, in _monitor
  File "logging\handlers.py", line 1424, in dequeue
  File "multiprocessing\queues.py", line 94, in get
  File "multiprocessing\connection.py", line 216, in recv_bytes
  File "multiprocessing\connection.py", line 321, in _recv_bytes
EOFError

"""
# TODO: Add image output directory tree item to be placed anywhere
#  eg. placed in preset will render preset to this directory, placed in render_preset will render presets not
#  containing out_dir_item to that dir
# TODO: Rename, Renumber Images from different RenderPresets


def initialize_log_listener(logging_queue):
    global LOGGER
    LOGGER = init_logging(MAIN_LOGGER_NAME)

    # This will move all handlers from LOGGER to the queue listener
    log_listener = setup_log_queue_listener(LOGGER, logging_queue)

    return log_listener


def shutdown(log_listener):
    #
    # ---- CleanUp ----
    # We do this just to prevent the IDE from deleting the imports
    gui_resource.qCleanupResources()
    darkstyle.qCleanupResources()

    # Shutdown logging and remove handlers
    LOGGER.info('Shutting down log queue listener and logging module.')

    log_listener.stop()
    logging.shutdown()


def main():
    multiprocessing.freeze_support()
    if FROZEN:
        # Set Exception hook
        sys.excepthook = KnechtExceptionHook.exception_hook

    #
    # ---- StartUp ----
    # Start log queue listener in it's own thread
    logging_queue = Queue(-1)
    setup_logging(logging_queue)
    log_listener = initialize_log_listener(logging_queue)
    log_listener.start()

    # Setup KnechtSettings logger
    delayed_log_setup()

    LOGGER.debug('---------------------------------------')
    LOGGER.debug('Application start.')

    # Update version in settings
    KnechtSettings.app['version'] = VERSION

    # Load GUI resource paths
    if not KnechtSettings.load_ui_resources():
        LOGGER.fatal('Can not locate UI resource files! Shutting down application.')
        shutdown(log_listener)
        return

    #
    #
    # ---- Start application ----
    app = KnechtApp(VERSION, logging_queue)
    app.setApplicationName('RenderKnecht')
    app.setApplicationDisplayName(app.applicationName())
    app.setApplicationVersion(VERSION)
    result = app.exec_()
    #
    #

    #
    #
    # ---- Application Result ----
    LOGGER.debug('---------------------------------------')
    LOGGER.debug('Qt application finished with exitcode %s', result)
    KnechtSettings.save()

    #
    #
    shutdown(log_listener)

    sys.exit(result)


if __name__ == '__main__':
    main()
