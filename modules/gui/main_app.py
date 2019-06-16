import logging
import sys

from PySide2 import QtWidgets
from PySide2.QtCore import QFile, QTextStream, QTimer

from modules.globals import MAIN_LOGGER_NAME, Resource
from modules.gui.gui_utils import KnechtExceptionHook
from modules.gui.main_ui import KnechtWindow
from modules.gui.ui_resource import FontRsc, IconRsc
from modules.gui.ui_splash_screen import show_splash_screen_movie
from modules.gui.widgets.message_box import AskToContinueCritical, GenericErrorBox
from modules.knecht_deltagen import SendToDeltaGen
from modules.knecht_render import KnechtRender
from modules.knecht_session import KnechtSession
from modules.language import get_translation
from modules.log import init_logging, setup_logging
from modules.settings import KnechtSettings

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


def load_style(app):
    # Load font size
    if not KnechtSettings.app.get('font_size'):
        KnechtSettings.app['font_size'] = FontRsc.regular_pixel_size

    FontRsc.init(KnechtSettings.app['font_size'])
    app.setFont(FontRsc.regular)

    # Default fallback style
    if not KnechtSettings.app.get('app_style'):
        KnechtSettings.app['app_style'] = 'windowsvista'

    # Load saved style
    if KnechtSettings.app.get('app_style').casefold() == 'fusion-dark':
        # Set Dark Fusion Style
        app.set_dark_style()
    else:
        # Set Default WindowsVista Style
        app.set_default_style()


class KnechtApp(QtWidgets.QApplication):
    def __init__(self, version, logging_queue):
        super(KnechtApp, self).__init__(sys.argv)

        splash = show_splash_screen_movie(self)

        self.version = version
        self.logging_queue = logging_queue

        # History widget will set active Undo Stack on view change
        self.undo_grp = QtWidgets.QUndoGroup(self)

        # -- Main Window --
        self.ui = KnechtWindow(self)
        self.ui.closeEvent = self.ui_close_event
        load_style(self)

        # -- Init DeltaGen thread --
        self.send_dg = SendToDeltaGen(self.ui)

        # -- Init Rendering Controller spawning rendering threads --
        self.render_dg = KnechtRender(self.ui)

        # -- Exception error box --
        self.error_message_box = GenericErrorBox(self.ui)

        # Prepare exception handling
        KnechtExceptionHook.app = self
        KnechtExceptionHook.setup_signal_destination(self.report_exception)

        # -- Show main window --
        self.ui.show()

        self.aboutToQuit.connect(self.about_to_quit)

        splash.finish(self.ui)

        # Applying the style before showing the main window will not update
        # the menu font sizes
        self.setFont(FontRsc.regular)

        self.session_handler = None

        # Restore SessionData
        QTimer.singleShot(50, self.init_session)

    def ui_close_event(self, close_event):
        """ Handle the MainWindow close event """
        confirm_close = True

        # -- Check for running Render Process
        if self.render_dg.is_running():
            box = AskToContinueCritical(self.ui)
            self.ui.play_warning_sound()

            confirm_close = not box.ask(
                title=_('Anwendung beenden'),
                txt=_('Achtung! Ein Render Vorgang läuft.<br><br>'
                      'Der Vorgang wird durch das Beenden abgebrochen.<br><br>'
                      'Soll die Anwendung wirklich beendet werden?'),
                ok_btn_txt=_('Abbrechen'),
                abort_btn_txt=_('Beenden erzwingen')
                )

            if confirm_close:
                self.render_dg.abort()
            else:
                close_event.ignore()
                return

        # -- Check for running DeltaGen Process
        if self.send_dg.is_running() and not confirm_close:
            box = AskToContinueCritical(self.ui)
            self.ui.play_warning_sound()
            confirm_close = box.ask(
                title=_('Anwendung beenden'),
                txt=_('Achtung! Ein laufender Prozess sendet Daten an DeltaGen.<br><br>'
                      'Soll die Anwendung wirklich beendet werden?'),
                ok_btn_txt=_('Beenden erzwingen'),
                abort_btn_txt=_('Abbrechen')
                )

        close_event.ignore()

        if confirm_close:
            self.save_session()
            self.quit()

    def init_session(self):
        self.session_handler = KnechtSession(self.ui, idle_save=True)
        self.session_handler.restore()

    def save_session(self):
        self.session_handler.save()

    def report_exception(self, msg):
        """ Receives KnechtExceptHook exception signal """
        msg = _('<h3>Hoppla!</h3>Eine schwerwiegende Anwendungsausnahme ist aufgetreten. Speichern Sie '
                'Ihre Daten und starten Sie die Anwendung neu.<br><br>') + msg.replace('\n', '<br>')

        self.error_message_box.setWindowTitle(_('Anwendungsausnahme'))
        self.error_message_box.set_error_msg(msg)
        self.ui.play_warning_sound()
        self.ui.app.alert(self.ui, 8000)

        self.error_message_box.exec_()

    def produce_exception(self):
        """ Produce an exception to test exception handling """
        a = 1 / 0

    def set_debug_log_level(self):
        self.ui.msg('A group of highly trained monkeys has been dispatched to type more log messages. '
                    'Large tree performance will be decreased significantly.', 10000)

        LOGGER.warning('Current log level: %s', logging.getLevelName(LOGGER.getEffectiveLevel()))
        setup_logging(self.logging_queue, overwrite_level='DEBUG')
        main_logger = logging.getLogger(MAIN_LOGGER_NAME)
        main_logger.setLevel(logging.DEBUG)
        LOGGER.warning('This logger level: %s', logging.getLevelName(LOGGER.getEffectiveLevel()))
        LOGGER.warning('Main logger level: %s', logging.getLevelName(main_logger.getEffectiveLevel()))

    def about_to_quit(self):
        LOGGER.debug('QApplication is about to quit.')
        self.ui.system_tray.hide()
        self.ui.system_tray.deleteLater()

        self.send_dg.end_thread()

    def set_default_style(self):
        self.setStyleSheet(None)
        KnechtSettings.app['app_style'] = 'windowsvista'
        IconRsc.update_icons(self.ui)
        self.setStyle('windowsvista')

    def set_dark_style(self):
        f = QFile(Resource.darkstyle)

        if not f.exists():
            LOGGER.error("Unable to load dark stylesheet, file not found in resources")
            return
        else:
            f.open(QFile.ReadOnly | QFile.Text)
            ts = QTextStream(f)
            stylesheet = ts.readAll()

            self.setStyleSheet(stylesheet)
            KnechtSettings.app['app_style'] = 'fusion-dark'
            IconRsc.update_icons(self.ui)

            self.setStyle('Fusion')
