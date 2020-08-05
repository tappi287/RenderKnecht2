from datetime import datetime

from PySide2.QtCore import QObject, QTimer
from PySide2.QtWidgets import QLineEdit, QTextBrowser

from modules import KnechtSettings
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class KnechtWolkeUi(QObject):
    debounce = QTimer()
    debounce.setSingleShot(True)
    debounce.setInterval(3500)

    def __init__(self, ui):
        """

        :param modules.gui.main_ui.KnechtWindow ui:
        """
        super(KnechtWolkeUi, self).__init__(ui)
        self.ui = ui
        self.ui.pageDescription.setText(_('Verbindung zur KnechtWolke herstellen um PR-Strings aus der Wolke zu senden.'))
        self.ui.autostartCheckBox.setText(_('Beim Anwendungsstart automatisch verbinden'))
        self.ui.connectLabel.setText(_('Verbindung herstellen'))

        # --- Prepare Host/Port/User edit ---
        self.ui.hostEdit.setText(KnechtSettings.wolke.get('host'))
        self.ui.portEdit.setText(KnechtSettings.wolke.get('port'))
        self.ui.userEdit.setText(KnechtSettings.wolke.get('user'))

        self.ui.hostEdit.textChanged.connect(self.update_host)
        self.ui.portEdit.textChanged.connect(self.update_port)
        self.ui.userEdit.textChanged.connect(self.update_user)

        # -- Connect Button --
        self.ui.connectBtn.setText(_('Verbinden'))
        self.ui.connectBtn.pressed.connect(self.wolke_connect)

        # -- Setup Text Browser --
        self.txt: QTextBrowser = self.ui.textBrowser
        QTimer.singleShot(1000, self.delayed_setup)

    @staticmethod
    def update_host(host):
        KnechtSettings.wolke['host'] = host

    @staticmethod
    def update_port(port):
        KnechtSettings.wolke['port'] = port

    @staticmethod
    def update_user(user):
        KnechtSettings.wolke['user'] = user

    def delayed_setup(self):
        self.ui.app.send_dg.socketio_status.connect(self.update_txt)

    def wolke_connect(self):
        self.ui.app.send_dg.start_socketio.emit()

    def update_txt(self, message):
        current_time = datetime.now().strftime('(%H:%M:%S)')
        self.txt.append(f'{current_time} {message}')
