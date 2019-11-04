import logging
from pathlib import Path
from queue import Queue
from threading import Thread

from PySide2.QtCore import QObject, Signal, Slot

from modules.globals import DeltaGenResult, MAIN_LOGGER_NAME
from modules.knecht_objects import KnechtVariantList
from modules.language import get_translation
from modules.log import init_logging, setup_logging, setup_log_queue_listener
from modules.plmxml import PlmXml
from modules.plmxml.configurator import PlmXmlConfigurator
from private.plmxml_example_data import example_pr_string, plm_xml_file

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class KnechtPlmXmlController(QObject):
    send_finished = Signal(int)
    no_connection = Signal()
    status = Signal(str)
    progress = Signal(int)
    plmxml_finished = Signal(int)

    def __init__(self, variants_ls: KnechtVariantList):
        super(KnechtPlmXmlController, self).__init__()
        self.variants_ls = variants_ls
        self.send_in_progress = False

        self.send_finished.connect(self._thread_finished)

        self.last_result = str()

    def set_last_result(self, msg: str):
        self.last_result = msg

    def start(self):
        t = KnechtUpdatePlmXml(self)
        t.start()

        self.send_in_progress = True

    def _thread_finished(self, result: int):
        self.send_in_progress = False
        self.plmxml_finished.emit(result)


class KnechtUpdatePlmXmlSignals(QObject):
    send_finished = Signal(int)
    no_connection = Signal()
    status = Signal(str)
    progress = Signal(int)
    plmxml_result = Signal(str)


class KnechtUpdatePlmXml(Thread):
    def __init__(self, controller: KnechtPlmXmlController):
        super(KnechtUpdatePlmXml, self).__init__()
        self.controller = controller
        self.variants_ls = controller.variants_ls
        self.signals = KnechtUpdatePlmXmlSignals()

    @staticmethod
    def _create_pr_string_from_variants(variants_ls: KnechtVariantList) -> str:
        pr_conf = ''

        for variant in variants_ls.variants:
            pr_conf += f'+{variant.name}'

        return pr_conf

    def _setup_signals(self):
        self.signals.send_finished.connect(self.controller.send_finished)
        self.signals.status.connect(self.controller.status)
        self.signals.progress.connect(self.controller.progress)
        self.signals.no_connection.connect(self.controller.no_connection)

        self.signals.plmxml_result.connect(self.controller.set_last_result)

    def run(self) -> None:
        self._setup_signals()

        result = DeltaGenResult.send_success
        file = Path(self.variants_ls.plm_xml_path)

        # -- Parse a PlmXml file, collecting product instances and LookLibrary
        plm_xml_instance = PlmXml(file)

        if not plm_xml_instance.is_valid:
            LOGGER.error(plm_xml_instance.error)
            self.signals.status.emit(plm_xml_instance.error)
            self.signals.plmxml_result.emit(plm_xml_instance.error)
            self.signals.send_finished.emit(DeltaGenResult.cmd_failed)
            return

        # -- Configure the PlmXml product instances and LookLibrary with a configuration string
        conf = PlmXmlConfigurator(plm_xml_instance, self._create_pr_string_from_variants(self.variants_ls))

        # -- Request to show the updated configuration in DeltaGen, will block
        if not conf.request_delta_gen_update():
            errors = '\n'.join(conf.errors)
            LOGGER.error(errors)
            self.signals.status.emit(errors)
            self.signals.plmxml_result.emit(errors)
            result = DeltaGenResult.send_failed

        if result == DeltaGenResult.send_success:
            self.signals.plmxml_result.emit(conf.status_msg)
        self.signals.send_finished.emit(result)


# -----------------------------------------------------
# Everything below is for executing this as test script

def _initialize_log_listener(logging_queue):
    global LOGGER
    LOGGER = init_logging(MAIN_LOGGER_NAME)

    # This will move all handlers from LOGGER to the queue listener
    log_listener = setup_log_queue_listener(LOGGER, logging_queue)

    return log_listener


if __name__ == '__main__':
    """
       Example script to parse a PlmXml and send a AsConnector Request
       PR String Configuration can be entered/pasted while running.
    """
    log_queue = Queue()
    setup_logging(log_queue)
    log_listener = _initialize_log_listener(log_queue)
    log_listener.start()

    # -- Parse a PlmXml file, collecting product instances and LookLibrary
    plm_xml = PlmXml(plm_xml_file)

    # -- Let the User enter a PR String for testing
    LOGGER.info('Enter PR String(leave blank for example string):')
    pr_string = input('>>>:')

    if not pr_string:
        pr_string = example_pr_string

    # -- Configure the PlmXml product instances and LookLibrary with a configuration string
    config = PlmXmlConfigurator(plm_xml, pr_string)

    # -- Request to show the updated configuration in DeltaGen, will block
    if not config.request_delta_gen_update():
        for err in config.errors:
            LOGGER.error(err)

    log_listener.stop()
    logging.shutdown()
