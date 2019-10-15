import os
import datetime
import time
from multiprocessing import Process
from pathlib import Path
from subprocess import Popen
from threading import Thread

import requests
from PySide2.QtCore import QObject, QTimer, Signal, Slot, Qt

from modules.globals import UPDATE_DIR_URL, UPDATE_INSTALL_FILE, UPDATE_VERSION_FILE
from modules.globals import get_settings_dir, get_current_modules_dir, FROZEN
from modules.gui.widgets.message_box import AskToContinue
from modules.gui.widgets.path_util import path_exists
from modules.language import get_translation
from modules.log import init_logging
from modules.settings import KnechtSettings

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


def _start_knecht_app():
    app_path = Path(os.path.join(get_current_modules_dir(), 'RenderKnecht.exe'))
    time.sleep(2)
    start_app(app_path)


def start_app(app_path: Path):
    if path_exists(app_path) and app_path.is_file():
        Popen(app_path.as_posix())


def restart_knecht_app(ui):
    """

    :param modules.gui.main_ui.KnechtWindow ui:
    :return:
    """
    if not FROZEN:
        print('Can not restart in Debug environment.')
        return

    ui.close()
    p = Process(target=_start_knecht_app)
    p.start()


class _KnechtUpdateThreadSignals(QObject):
    update_ready = Signal(Path)
    update_failed = Signal()
    already_up_to_date = Signal()
    new_version = Signal(str)


class _KnechtUpdateThread(Thread):
    def __init__(self, parent):
        super(_KnechtUpdateThread, self).__init__()
        self.parent = parent
        self.version = '0.00'

        self.signals = _KnechtUpdateThreadSignals()
        self.update_ready = self.signals.update_ready
        self.update_failed = self.signals.update_failed
        self.new_version = self.signals.new_version
        self.already_up_to_date = self.signals.already_up_to_date

    def run(self):
        # --- Download version info
        LOGGER.debug('Running update check.')

        version_txt_url = UPDATE_DIR_URL + UPDATE_VERSION_FILE

        r = requests.get(version_txt_url)

        if r.status_code != 200:
            self.update_failed.emit()
            return

        # --- Compare versions
        self._set_version(r.text)

        if not self._is_newer_version():
            LOGGER.info('Application version is up to date.')
            self.already_up_to_date.emit()
            return

        # --- CleanUp existing installers
        output_dir = Path(get_settings_dir())

        for file in output_dir.glob('*.exe'):
            try:
                os.remove(file.as_posix())
            except OSError as e:
                LOGGER.error(e)

        # --- Download Update installer
        installer_url = UPDATE_DIR_URL + UPDATE_INSTALL_FILE.format(version=self.version)

        r = requests.get(installer_url)

        if r.status_code != 200:
            self.update_failed.emit()
            return

        try:
            installer_file = output_dir / UPDATE_INSTALL_FILE.format(version=self.version)

            with open(installer_file, 'wb') as f:
                f.write(r.content)

            self.update_ready.emit(installer_file)
        except Exception as e:
            LOGGER.error(e)
            self.update_failed.emit()

        self.signals.deleteLater()

    def _is_newer_version(self) -> bool:
        if self.version > KnechtSettings.app['version']:
            return True
        return False

    def _set_version(self, version: str):
        LOGGER.info('Found remote version: %s', version)
        self.version = version
        self.new_version.emit(version)


class KnechtUpdate(QObject):
    update_available = Signal(str)

    remote_version = '0.00'
    remote_version_age = datetime.datetime.now()

    installer_file = Path('Dummy.exe')
    first_run = True

    def __init__(self, ui):
        """ Run an updater thread to check for new versions on remote path.

        :param modules.gui.main_ui.KnechtWindow ui:
        """
        super(KnechtUpdate, self).__init__(ui)
        self.ui = ui

        # Update check thread
        self.ut: _KnechtUpdateThread = None

        self.timeout = QTimer()
        self.timeout.setSingleShot(True)
        self.timeout.setInterval(3000)

        self.schedule_timer = QTimer()
        self.schedule_timer.setInterval(8000000)
        self.schedule_timer.setTimerType(Qt.VeryCoarseTimer)
        self.schedule_timer.timeout.connect(self.schedule_update)
        self.schedule_timer.start()

        self.last_update_check = datetime.datetime.now()

    def schedule_update(self):
        """ Daily update check """
        delta = datetime.datetime.now() - self.last_update_check

        if delta > datetime.timedelta(days=1):
            LOGGER.info('Running scheduled update check after: %s', delta)
            self.run_update()

    def _init_thread(self):
        # Update check thread
        self.ut = _KnechtUpdateThread(self)

        # Update thread signals
        self.ut.already_up_to_date.connect(self._already_latest_version)
        self.ut.update_failed.connect(self._update_error)
        self.ut.update_ready.connect(self._set_update_available)
        self.ut.new_version.connect(self._set_remote_version)

    def run_update(self):
        """
            If an updated installer is available: ask user to execute it.
            Otherwise run update thread to check for newer versions
        """
        # Make sure this is not called within timeout
        if self.timeout.isActive():
            return
        self.timeout.start()
        self.first_run = False
        self.last_update_check = datetime.datetime.now()

        # Exit on running thread
        if self.is_running():
            LOGGER.info('Can not check for updates while update thread is running!')
            return

        # Run update if already available
        if self._is_update_ready():
            if not self._ask_to_run():
                return
            self._execute_update()
            return

        # Check if already up to date
        if self.is_up_to_date():
            self._already_latest_version()
            return

        self._init_thread()
        self.ut.start()
        self.ui.msg(_('Suche nach Anwendungs Updates gestartet.'))

    def is_up_to_date(self) -> bool:
        """ Return True if the remote version equals current version """
        delta = datetime.datetime.now() - self.remote_version_age

        if delta > datetime.timedelta(hours=1):
            # Remote version info is older than 1 hour
            return False

        if self.remote_version == KnechtSettings.app['version']:
            return True
        return False

    def is_running(self):
        """ Determine wherever a Update thread is running. """
        if self.ut is not None:
            if self.ut.is_alive():
                return True
        return False

    def _is_update_ready(self) -> bool:
        if path_exists(self.installer_file):
            if self.remote_version > KnechtSettings.app['version']:
                return True
        return False

    def _execute_update(self):
        args = [self.installer_file.as_posix(), '/SILENT', '/CLOSEAPPLICATIONS', '/RESTARTAPPLICATIONS']
        try:
            Popen(args)
            LOGGER.info('Running Update Installer: %s', args)
        except Exception as e:
            LOGGER.error('Could not run update installer. %s', e)
            return

        # Close application
        self.ui.close()

    @Slot(Path)
    def _set_update_available(self, installer_file: Path):
        self.installer_file = installer_file

        if self._is_update_ready():
            self.update_available.emit(self.remote_version)
            self._show_notification()

    @Slot(str)
    def _set_remote_version(self, version: str):
        self.remote_version = version
        self.remote_version_age = datetime.datetime.now()

    @Slot()
    def _already_latest_version(self):
        self.ui.msg(_('Die Anwendung ist auf dem neusten Stand.'), 5000)

    @Slot()
    def _update_error(self):
        self.ui.msg(
            _('Aktualisierung konnte nicht durchgeführt werden.'),
            4000
            )

    def _ask_to_run(self) -> bool:
        msg_box = AskToContinue(self.ui)
        self.ui.play_hint_sound()

        if not msg_box.ask(
            title=_('App Update'),
            txt=_('Eine aktualisierte Version {} ist verfügbar.<br><br>'
                  'Möchten Sie die Aktualisierung jetzt durchführen?<br><br>'
                  'Die Anwendung muss für das Update beendet werden.'
                  ).format(self.remote_version),
            ok_btn_txt=_('Jetzt aktualisieren'),
            abort_btn_txt=_('Vielleicht später...'),
                ):
            # User wants to update later
            return False
        return True

    def _show_notification(self):
        def msg_callback():
            if self._ask_to_run():
                self._execute_update()

        self.ui.show_tray_notification(
            title=_('Aktualisierung'),
            message=_('Version {} ist bereit zur Installation.').format(self.remote_version),
            clicked_callback=msg_callback
            )
