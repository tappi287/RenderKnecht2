import logging
import sys
import signal
from multiprocessing import Queue, freeze_support

from PySide2.QtCore import Qt
from PySide2.QtWidgets import QApplication

from modules.globals import FROZEN, MAIN_LOGGER_NAME
from modules.gui.gui_utils import KnechtExceptionHook
from modules.gui.main_app import KnechtApp
from modules.gui.widgets.about_page import InfoMessage
from modules.log import init_logging, setup_log_queue_listener, setup_logging
from modules.settings import KnechtSettings, delayed_log_setup
from modules.gui.ui_resource import unpack_csb_dummy
from modules.singleton import SingleInstance
from ui import darkstyle, gui_resource

if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    print('Using high dpi Pixmaps')

VERSION = '1.572'

InfoMessage.ver = VERSION
InfoMessage.lic = 'GPL v3'
InfoMessage.auth = 'Stefan Tapper'
InfoMessage.mail = 'tapper.stefan@gmail.com'
InfoMessage.cred = ['Python Community', 'PyCharm Community Edition', 'Stackoverflow', 'PySide Docs']

# TODO: Implement PlmXml QA LookLibrary Targets != AsConnector2.targetGetAllNames
# should find Targets that are listed inside PlmXml but not available inside the DG Scene
# maybe even catch the error before configuring to prevent AsConnector Exception resulting
# in incomplete configurations.
# TODO: Rename, Renumber Images from different RenderPresets
# TODO: item deletion buggy, eg. load plm xml template, delete variants, but not ref, in preset
# TODO: delete newly created top level rows -> could not remove row


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
    s = SingleInstance(flavor_id='RenderKnecht2instance')  # will sys.exit(-1) if other instance is running

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

    # Unpack CSB Dummy Material
    if not unpack_csb_dummy():
        LOGGER.error('Could not unpack CSB Dummy Material into settings path!')

    #
    #
    # ---- Start application ----
    app = KnechtApp(VERSION, logging_queue)
    app.setApplicationName('RenderKnecht')
    app.setApplicationDisplayName(app.applicationName())
    app.setApplicationVersion(VERSION)

    # Register the signal handlers
    signal.signal(signal.SIGTERM, app.quit)
    signal.signal(signal.SIGINT, app.quit)

    result = app.exec_()

    #
    #
    # ---- Application DeltaGenResult ----
    LOGGER.debug('---------------------------------------')
    LOGGER.debug('Qt application finished with exitcode %s', result)
    KnechtSettings.save()

    #
    #
    shutdown(log_listener)

    del s
    sys.exit(result)


if __name__ == '__main__':
    freeze_support()  # it is important to have this line exactly here << !!!
    main()
