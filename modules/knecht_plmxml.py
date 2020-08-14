from pathlib import Path
from threading import Thread
from typing import Tuple

from PySide2.QtCore import QObject, Signal

from modules.globals import DeltaGenResult
from modules.knecht_objects import KnechtVariantList
from modules.language import get_translation
from modules.log import init_logging
from modules.plmxml import PlmXml
from modules.plmxml.configurator import PlmXmlConfigurator
from modules.plmxml.connector import AsConnectorConnection
from modules.plmxml.request import AsSceneSetActiveRequest, AsSceneGetAllRequest, AsSceneGetActiveRequest
from modules.plmxml.utils import create_pr_string_from_variants

# from private.plmxml_example_data import example_pr_string, plm_xml_file

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class KnechtPlmXmlController(QObject):
    send_finished = Signal(int)
    no_connection = Signal()
    status = Signal(str, int)
    progress = Signal(int)
    plmxml_result = Signal(str)
    scene_active_result = Signal(str, list)

    def __init__(self, variants_ls: KnechtVariantList):
        super(KnechtPlmXmlController, self).__init__()
        self.variants_ls = variants_ls
        self.send_in_progress = False
        self.active_scene = ''

        self.send_finished.connect(self._thread_finished)
        self.scene_active_result.connect(self._active_scene_result)

    def start_configuration(self):
        """ Skip for now, active scene has to last loaded scene
            or AsConnector will send garbage.
        if not self.active_scene:
            self.plmxml_result.emit(
                _('Keine aktive Szene gesetzt. Bitte aktive AsConnector '
                  'Szene im DeltaGen Menü auswählen.')
            )
            return
        """

        t = KnechtUpdatePlmXml(self)
        t.start()

        self.send_in_progress = True

    def start_get_set_active_scenes(self, set_active_scene: str=None):
        """ Request a list of available scene + str of currently active scene
            and, if set, request the provided <set_active_scene> to be set as active scene.
            Will emit Signal scene_result on success or no connection otherwise.

        :param str set_active_scene: Scene name of the scene to set active
        """
        t = KnechtUpdateActiveScene(self, set_active_scene)
        t.start()

    def _active_scene_result(self, active_scene: str):
        self.active_scene = active_scene

    def _thread_finished(self, result: int):
        LOGGER.debug('KnechtUpdatePlmXml thread finished with result:\n%s', result)
        self.send_in_progress = False


class _KnechtUpdateActiveSceneSignals(QObject):
    no_connection = Signal()
    scene_result = Signal(str, list)


class KnechtUpdateActiveScene(Thread):
    def __init__(self, controller, set_active_scene: str=None):
        """ Run request to get all scenes + currently active scene.
            If set_active_scene provided, request this scene_name to be set as active.

        :param KnechtPlmXmlController controller: thread controller
        :param str set_active_scene: either a scene name or empty string/none for no SetActive scene request
        """
        super(KnechtUpdateActiveScene, self).__init__()
        self.signals = _KnechtUpdateActiveSceneSignals()
        self.set_active_scene = set_active_scene or ''
        self.controller = controller

    def _setup_signals(self):
        self.signals.no_connection.connect(self.controller.no_connection)
        self.signals.scene_result.connect(self.controller.scene_active_result)

    def start(self) -> None:
        self._setup_signals()
        active_scene, scene_list = self._request_scene_list()

        # -- Emit Results
        self.signals.scene_result.emit(active_scene, scene_list)

        if not active_scene and not scene_list:
            self.signals.no_connection.emit()
            return

        if self.set_active_scene:
            result = self._set_scene_active_request(self.set_active_scene)
            if not result:
                self.signals.no_connection.emit()

    @staticmethod
    def _set_scene_active_request(scene_name: str):
        """ Request AsConnector to set scene with scene_name active """
        as_conn = AsConnectorConnection()
        if not as_conn.check_connection():
            return False

        set_active_req = AsSceneSetActiveRequest(scene_name)
        return as_conn.request(set_active_req)

    @staticmethod
    def _request_scene_list() -> Tuple[str, list]:
        as_conn = AsConnectorConnection()
        if not as_conn.check_connection():
            return str(), list()

        get_all_req = AsSceneGetAllRequest()
        result = as_conn.request(get_all_req)

        if not result:
            return str(), list()

        get_active_scene_req = AsSceneGetActiveRequest()
        result = as_conn.request(get_active_scene_req)
        if not result:
            return str(), list()

        active_scene = get_active_scene_req.result
        scenes = get_all_req.result
        return active_scene, scenes


class _KnechtUpdatePlmXmlSignals(QObject):
    send_finished = Signal(int)
    no_connection = Signal()
    status = Signal(str, int)
    progress = Signal(int)
    plmxml_result = Signal(str)


class KnechtUpdatePlmXml(Thread):
    def __init__(self, controller: KnechtPlmXmlController):
        super(KnechtUpdatePlmXml, self).__init__()
        self.controller = controller
        self.variants_ls = controller.variants_ls
        self.signals = _KnechtUpdatePlmXmlSignals()

    def _setup_signals(self):
        self.signals.send_finished.connect(self.controller.send_finished)
        self.signals.status.connect(self.controller.status)
        self.signals.progress.connect(self.controller.progress)
        self.signals.no_connection.connect(self.controller.no_connection)
        self.signals.plmxml_result.connect(self.controller.plmxml_result)

    @staticmethod
    def _validate_scene(conf: PlmXmlConfigurator):
        request_successful, missing_nodes, missing_targets = conf.validate_scene_vs_plmxml()

        if request_successful and missing_nodes:
            scene_result = _('DeltaGen Szene stimmt nicht mit PlmXml überein. Fehlende Knoten:\n')
            scene_result += '\n'.join(
                [f'Name: {m.name} LincId: {m.linc_id}' for m in missing_nodes[:20]]
                )
            if len(missing_nodes) > 20:
                scene_result += _('\n..und {} weitere Knoten.').format(len(missing_nodes[20:]))
            scene_result += _('\nDiese Prüfung kann in den DeltaGen Optionen deaktiviert werden.')

            return False, scene_result
        elif request_successful and not missing_nodes:
            scene_result = _('DeltaGen Szenenstruktur erfolgreich mit PlmXml Struktur abgeglichen.')
        else:
            scene_result = _('Konnte DeltaGen Szene nicht mit PlmXml abgleichen. Keine Verbindung zum AsConnector2.')

        if missing_targets:
            scene_result += _('\nDie folgenden Material Targets fehlen oder sind nicht geladen:\n')
            scene_result += f'{"; ".join(missing_targets)}'

        return True, scene_result

    def run(self) -> None:
        self._setup_signals()

        result = DeltaGenResult.send_success
        file = Path(self.variants_ls.plm_xml_path)

        self.signals.status.emit(_('Konfiguriere PlmXml Instanz'), 4000)

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
        self.signals.status.emit(_('Validiere DeltaGen Szenenstruktur gegen PlmXml Struktur ...'), 8000)
        scene_valid, scene_result = self._validate_scene(conf)

        if not scene_valid:
            self.signals.plmxml_result.emit(scene_result)
            self.signals.send_finished.emit(DeltaGenResult.cmd_failed)
            return

        # -- Request to show the updated configuration in DeltaGen, will block
        self.signals.status.emit(_('Konfiguriere DeltaGen Szenenstruktur ...'), 8000)
        if not conf.request_delta_gen_update():
            errors = '\n'.join(conf.errors)
            LOGGER.error(errors)
            self.signals.plmxml_result.emit(errors)
            result = DeltaGenResult.send_failed

        if result == DeltaGenResult.send_success:
            self.signals.plmxml_result.emit(conf.status_msg)
        self.signals.send_finished.emit(result)
