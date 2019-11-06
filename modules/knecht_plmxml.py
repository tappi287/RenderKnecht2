import logging
from pathlib import Path
from queue import Queue
from threading import Thread

from PySide2.QtCore import QObject, Signal, Slot

from modules import KnechtSettings
from modules.globals import DeltaGenResult, MAIN_LOGGER_NAME
from modules.knecht_objects import KnechtVariantList
from modules.language import get_translation
from modules.log import init_logging, setup_logging, setup_log_queue_listener
from modules.plmxml import PlmXml
from modules.plmxml.configurator import PlmXmlConfigurator
from modules.plmxml.utils import create_pr_string_from_variants
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
    plmxml_result = Signal(str)

    def __init__(self, variants_ls: KnechtVariantList):
        super(KnechtPlmXmlController, self).__init__()
        self.variants_ls = variants_ls
        self.send_in_progress = False

        self.send_finished.connect(self._thread_finished)

    def start(self):
        t = KnechtUpdatePlmXml(self)
        t.start()

        self.send_in_progress = True

    def _thread_finished(self, result: int):
        LOGGER.debug('KnechtUpdatePlmXml thread finished with result:\n%s', result)
        self.send_in_progress = False


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

    def _setup_signals(self):
        self.signals.send_finished.connect(self.controller.send_finished)
        self.signals.status.connect(self.controller.status)
        self.signals.progress.connect(self.controller.progress)
        self.signals.no_connection.connect(self.controller.no_connection)
        self.signals.plmxml_result.connect(self.controller.plmxml_result)

    @staticmethod
    def _validate_scene(conf: PlmXmlConfigurator):
        request_successful, missing_nodes = conf.validate_scene_vs_plmxml()

        if request_successful and missing_nodes:
            scene_result = _('DeltaGen Szene stimmt nicht mit PlmXml überein. Fehlende Knoten:\n')
            scene_result += '\n'.join(
                [f'Name: {m.product_instance.name} LincId: {m.product_instance.linc_id}' for m in missing_nodes[:20]]
                )

            if len(missing_nodes) > 20:
                scene_result += _('\n..und {} weitere Knoten.').format(len(missing_nodes[20:]))

            return False, scene_result
        elif request_successful and not missing_nodes:
            scene_result = _('DeltaGen Szene erfolgreich mit PlmXml abgeglichen.')
        else:
            scene_result = _('Konnte DeltaGen Szene nicht mit PlmXml abgleichen. Keine Verbindung zum AsConnector2.')

        return True, scene_result

    def run(self) -> None:
        self._setup_signals()

        result = DeltaGenResult.send_success
        file = Path(self.variants_ls.plm_xml_path)

        self.signals.status.emit(_('Konfiguriere PlmXml Instanz'))

        # -- Parse a PlmXml file, collecting product instances and LookLibrary
        plm_xml_instance = PlmXml(file)

        if not plm_xml_instance.is_valid:
            LOGGER.error(plm_xml_instance.error)
            self.signals.plmxml_result.emit(plm_xml_instance.error)
            self.signals.send_finished.emit(DeltaGenResult.cmd_failed)
            return

        # -- Configure the PlmXml product instances and LookLibrary with a configuration string
        conf = PlmXmlConfigurator(plm_xml_instance, create_pr_string_from_variants(self.variants_ls))

        # -- Validate Scene
        if KnechtSettings.dg.get('validate_plmxml_scene'):
            self.signals.status.emit(_('Validiere DeltaGen Szenenstruktur gegen PlmXml Struktur.'))
            scene_valid, scene_result = self._validate_scene(conf)

            if not scene_valid:
                self.signals.plmxml_result.emit(scene_result)
                self.signals.send_finished.emit(DeltaGenResult.cmd_failed)
                return
            else:
                self.signals.status.emit(scene_result)

        # -- Request to show the updated configuration in DeltaGen, will block
        if not conf.request_delta_gen_update():
            errors = '\n'.join(conf.errors)
            LOGGER.error(errors)
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
    ll = setup_log_queue_listener(LOGGER, logging_queue)

    return ll


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
