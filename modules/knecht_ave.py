from threading import Thread

from PySide2.QtCore import QObject, Signal

from modules.aveconnector.connector import AVEConnection
from modules.aveconnector.request import AVEConfigurationRequest
from modules.globals import DeltaGenResult
from modules.knecht_objects import KnechtVariantList
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class KnechtAVEController(QObject):
    send_finished = Signal(int)
    status = Signal(str, int)
    progress = Signal(int)
    ave_result = Signal(str)

    def __init__(self, variants_ls: KnechtVariantList):
        super(KnechtAVEController, self).__init__()
        self.variants_ls = variants_ls
        self.send_in_progress = False

        self.send_finished.connect(self._thread_finished)

    def start_configuration(self):
        t = KnechtUpdateAVE(self)
        t.start()

        self.send_in_progress = True

    def _thread_finished(self, result: int):
        LOGGER.debug('KnechtUpdateAVE thread finished with result:\n%s', result)
        self.send_in_progress = False


class _KnechtUpdateAVESignals(QObject):
    send_finished = Signal(int)
    status = Signal(str, int)
    progress = Signal(int)
    ave_result = Signal(str)


class KnechtUpdateAVE(Thread):
    def __init__(self, controller: KnechtAVEController):
        super(KnechtUpdateAVE, self).__init__()
        self.controller = controller
        self.as_conn = None
        self.variants_ls = controller.variants_ls
        self.signals = _KnechtUpdateAVESignals()

    def _setup_signals(self):
        self.signals.send_finished.connect(self.controller.send_finished)
        self.signals.status.connect(self.controller.status)
        self.signals.progress.connect(self.controller.progress)
        self.signals.ave_result.connect(self.controller.ave_result)

    def run(self) -> None:
        self._setup_signals()

        # -- Create AVE Connection
        conf = create_ave_conf_from_variants(self.variants_ls)
        r = AVEConfigurationRequest(conf)
        ave_conn = AVEConnection()

        msg = _('Sende Varianten an AVE Instanz')
        msg += f'\n{",".join(conf)}'
        self._update_status(msg)

        if not ave_conn.request(r, False):
            # -- Error
            msg = _('Fehler beim Senden an AVE')
            msg += f'\n{ave_conn.error}'
            self._update_status(msg)
            self.signals.ave_result.emit(msg)
            self.signals.send_finished.emit(DeltaGenResult.send_failed)
            return

        # -- Success
        self.signals.ave_result.emit('Konfiguration an AVE gesendet')
        self.signals.send_finished.emit(DeltaGenResult.send_success)

    def _update_status(self, message: str):
        self.signals.status.emit(message, 5000)


def create_ave_conf_from_variants(variants_ls: KnechtVariantList) -> list:
    pr_conf = list()

    for variant in variants_ls.variants:
        pr_conf.append(f'{variant.name}')

    return pr_conf