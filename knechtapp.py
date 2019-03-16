import sys
import logging

from PySide2.QtCore import Qt
from PySide2.QtWidgets import QApplication

from modules.gui.gui_utils import KnechtExceptionHook
from ui import gui_resource
from ui import darkstyle
from multiprocessing import Queue
from modules.log import init_logging, setup_log_queue_listener, setup_logging
from modules.settings import KnechtSettings, delayed_log_setup
from modules.globals import FROZEN
from modules.gui.main_app import KnechtApp


if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    print('Using high dpi Pixmaps')

VERSION = '0.61'

# TODO: Rename, Renumber Images from different RenderPresets


def initialize_log_listener(logging_queue):
    global LOGGER
    LOGGER = init_logging('knecht_main')

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
    app = KnechtApp(VERSION)
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
