from datetime import datetime

from PySide2.QtCore import QObject, QTimer, Signal
from PySide2.QtWidgets import QLineEdit, QTextBrowser

from modules import KnechtSettings
from modules.knecht_objects import KnechtVariantList
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
        self.ui.connectLabel.setText(_('Verbindung herstellen'))

        # --- Prepare Host/Port/User edit ---
        self.ui.hostEdit.setText(KnechtSettings.wolke.get('host'))
        self.ui.portEdit.setText(KnechtSettings.wolke.get('port'))
        self.ui.userEdit.setText(KnechtSettings.wolke.get('user'))
        self.ui.tokenEdit.setText(KnechtSettings.wolke.get('token'))

        self.ui.hostEdit.textChanged.connect(self.update_host)
        self.ui.portEdit.textChanged.connect(self.update_port)
        self.ui.userEdit.textChanged.connect(self.update_user)
        self.ui.tokenEdit.textChanged.connect(self.update_token)

        # -- Connect Button --
        self.ui.connectBtn.setText(_('Verbinden'))
        self.ui.connectBtn.pressed.connect(self.wolke_connect)
        self.ui.disconnectBtn.setText(_('Trennen'))
        self.ui.disconnectBtn.pressed.connect(self.wolke_disconnect)
        self.ui.disconnectBtn.setEnabled(False)

        # -- Autostart --
        self.ui.autostartCheckBox.setText(_('Beim Anwendungsstart automatisch verbinden'))
        self.ui.autostartCheckBox.setChecked(KnechtSettings.wolke.get('autostart', False))
        self.ui.autostartCheckBox.toggled.connect(self.toggle_autostart)

        self.ui_elements = (self.ui.hostEdit, self.ui.portEdit, self.ui.userEdit, self.ui.connectBtn)

        # -- Setup Text Browser --
        self.txt: QTextBrowser = self.ui.textBrowser
        QTimer.singleShot(1000, self.delayed_setup)

        # -- Warning --
        self.txt.append(_('<b>ACHTUNG</b> Dieses Feature ist noch nicht für den produktiv Einsatz freigegeben. '
                          'Sockenströme verursachen weltumspannende Interpretierer Sperren! '
                          'Die Anwendung kann bei Verwendung jederzeit unvorhergesehen hängen. Vor dem testen '
                          'wichtige Dokumente sichern!'))

    def delayed_setup(self):
        self.ui.app.send_dg.socketio_status.connect(self.update_txt)
        self.ui.app.send_dg.socketio_connected.connect(self.connected)
        self.ui.app.send_dg.socketio_disconnected.connect(self.disconnected)
        self.ui.app.send_dg.socketio_send_variants.connect(self._send_variants)

        if KnechtSettings.wolke.get('autostart', False):
            self.wolke_connect()

    def connected(self):
        for ui_element in self.ui_elements:
            ui_element.setEnabled(False)
        self.ui.connectBtn.setText(_('Verbunden'))
        self.ui.disconnectBtn.setEnabled(True)

    def disconnected(self):
        for ui_element in self.ui_elements:
            ui_element.setEnabled(True)
        self.ui.connectBtn.setText(_('Verbinden'))
        self.ui.disconnectBtn.setEnabled(False)

    def _check_debounce(self) -> bool:
        if not self.debounce.isActive():
            self.debounce.start()
            return True
        return False

    def _send_variants(self, variant_ls: KnechtVariantList):
        self.ui.app.send_dg.send_variants(variant_ls)

    @staticmethod
    def toggle_autostart(v: bool):
        KnechtSettings.wolke['autostart'] = v

    @staticmethod
    def update_host(host):
        KnechtSettings.wolke['host'] = host

    @staticmethod
    def update_port(port):
        KnechtSettings.wolke['port'] = port

    @staticmethod
    def update_user(user):
        KnechtSettings.wolke['user'] = user

    @staticmethod
    def update_token(token):
        KnechtSettings.wolke['token'] = token

    def wolke_connect(self):
        if self._check_debounce():
            self.ui.app.send_dg.start_socketio.emit()

    def wolke_disconnect(self):
        if self._check_debounce():
            self.ui.app.send_dg.stop_socketio.emit()

    def update_txt(self, message):
        current_time = datetime.now().strftime('(%H:%M:%S)')
        self.txt.append(f'{current_time} {message}')
