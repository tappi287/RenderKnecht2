from pathlib import Path
from threading import Thread
from time import sleep
from typing import Tuple, Optional

from PySide2.QtCore import QObject, Signal
from plmxml import PlmXml, NodeInfo

from modules.globals import DeltaGenResult
from modules.knecht_objects import KnechtVariantList
from modules.settings import KnechtSettings
from modules.language import get_translation
from modules.log import init_logging
from modules.asconnector.configurator import PlmXmlConfigurator
from modules.asconnector.connector import AsConnectorConnection
from modules.asconnector.request import AsSceneSetActiveRequest, AsSceneGetAllRequest, AsSceneGetActiveRequest, \
    AsSceneLoadPlmXmlRequest, AsSceneCloseRequest

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
    material_dummy = Signal(NodeInfo)

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

    def start_get_set_active_scenes(self, set_active_scene: str = None):
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

    def run(self) -> None:
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

        set_active_req = AsSceneSetActiveRequest(scene_name)
        return as_conn.request(set_active_req)

    @staticmethod
    def _request_scene_list() -> Tuple[str, list]:
        as_conn = AsConnectorConnection()

        get_all_req = AsSceneGetAllRequest()
        result = as_conn.request(get_all_req)
        scenes = get_all_req.result

        if not result:
            return str(), scenes or list()

        get_active_scene_req = AsSceneGetActiveRequest()
        result = as_conn.request(get_active_scene_req)
        active_scene = get_active_scene_req.result

        if not result:
            return active_scene or str(), scenes or list()

        return active_scene, scenes


class _KnechtUpdatePlmXmlSignals(QObject):
    send_finished = Signal(int)
    no_connection = Signal()
    status = Signal(str, int)
    progress = Signal(int)
    plmxml_result = Signal(str)
    material_dummy = Signal(NodeInfo)


class KnechtUpdatePlmXml(Thread):
    def __init__(self, controller: KnechtPlmXmlController):
        super(KnechtUpdatePlmXml, self).__init__()
        self.controller = controller
        self.as_conn = None
        self.variants_ls = controller.variants_ls
        self.signals = _KnechtUpdatePlmXmlSignals()

    def _setup_signals(self):
        self.signals.send_finished.connect(self.controller.send_finished)
        self.signals.status.connect(self.controller.status)
        self.signals.progress.connect(self.controller.progress)
        self.signals.no_connection.connect(self.controller.no_connection)
        self.signals.plmxml_result.connect(self.controller.plmxml_result)
        self.signals.material_dummy.connect(self.controller.material_dummy)

    @staticmethod
    def _validate_scene(conf: PlmXmlConfigurator) -> Tuple[bool, str, Optional[NodeInfo]]:
        request_successful, missing_nodes, missing_targets, material_dummy = conf.validate_scene_vs_plmxml()

        if request_successful and missing_nodes:
            scene_result = _('DeltaGen Szene stimmt nicht mit PlmXml überein. Fehlende Knoten:')
            scene_result += '\n'
            scene_result += '\n'.join(
                [f'Name: {m.name} LincId: {m.linc_id}' for m in missing_nodes[:20]]
                )
            if len(missing_nodes) > 20:
                scene_result += '\n'
                scene_result += _('..und {} weitere Knoten.').format(len(missing_nodes[20:]))
            scene_result += '\n'
            scene_result += _('Diese Prüfung kann in den DeltaGen Optionen deaktiviert werden.')

            return False, scene_result, material_dummy
        elif request_successful and not missing_nodes:
            scene_result = _('DeltaGen Szenenstruktur erfolgreich mit PlmXml Struktur abgeglichen.')
        else:
            scene_result = _('Konnte DeltaGen Szene nicht mit PlmXml abgleichen. Keine Verbindung zum AsConnector2.')

        if missing_targets:
            scene_result += '\n'
            scene_result += _('Die folgenden Material Targets fehlen oder sind nicht geladen:')
            scene_result += '\n'
            scene_result += f'{"; ".join(missing_targets)}'

        return True, scene_result, material_dummy

    def run(self) -> None:
        self._setup_signals()

        result = DeltaGenResult.send_success
        plmxml_file = Path(self.variants_ls.plm_xml_path)

        # -- Check AsConnector connection
        self.as_conn = AsConnectorConnection()
        if not self.as_conn.check_connection():
            self._update_status(self.as_conn.error)
            return

        # -- Re-initialize AsConnector if active scene has changed --
        if not self._initialize_as_connector(plmxml_file):
            self._update_status(_('Konnte AsConnector nicht initialisieren. PlugIn geladen?'))
            return

        self._update_status(_('Konfiguriere PlmXml Instanz'))

        # -- Parse a PlmXml file, collecting product instances and LookLibrary
        plm_xml_instance = PlmXml(plmxml_file)

        if not plm_xml_instance.is_valid:
            LOGGER.error(plm_xml_instance.error)
            self.signals.plmxml_result.emit(plm_xml_instance.error)
            # - Move on for now so we will be abler to configure invalid PlmXml's
            # self.signals.send_finished.emit(DeltaGenResult.cmd_failed)
            # return

        # -- Configure the PlmXml product instances and LookLibrary with a configuration string
        conf = PlmXmlConfigurator(plm_xml_instance, create_pr_string_from_variants(self.variants_ls), self.as_conn,
                                  self._update_status)

        # -- Validate Scene
        self._update_status(_('Validiere DeltaGen Szenenstruktur gegen PlmXml Struktur ...'))
        scene_valid, scene_result, material_dummy = self._validate_scene(conf)

        # -- Report Material Dummy presence
        self.signals.material_dummy.emit(material_dummy)

        if not scene_valid:
            self.signals.plmxml_result.emit(scene_result)
            self.signals.send_finished.emit(DeltaGenResult.plmxml_mismatch)
            return

        # -- Request to show the updated configuration in DeltaGen, will block
        self._update_status(_('Konfiguriere DeltaGen Szenenstruktur ...'))
        if not conf.request_delta_gen_update():
            errors = '\n'.join(conf.errors)
            LOGGER.error(errors)
            self.signals.plmxml_result.emit(errors)
            result = DeltaGenResult.as_connector_error

        if result == DeltaGenResult.send_success:
            self.signals.plmxml_result.emit(conf.status_msg)
        self.signals.send_finished.emit(result)

    def _update_status(self, message: str):
        self.signals.status.emit(message, 5000)

    def _initialize_as_connector(self, plmxml_file: Path):
        """ Re-initialize AsConnector if active scene has changed:
            1. AsSceneGetActiveRequest
            2. AsSceneLoadPlmXmlRequest
            3. CloseScene
            -> AsConnector is now initialized to a new scene.
        """
        get_active_scene_req = AsSceneGetActiveRequest()
        scene_result = self.as_conn.request(get_active_scene_req, retry=False)
        active_scene = get_active_scene_req.result

        if scene_result and KnechtSettings.app.get('last_scene', '') == active_scene:
            if KnechtSettings.app.get('last_plmxml', '') == plmxml_file.name:
                return True

        if KnechtSettings.app.get('last_plmxml', '') == plmxml_file.name:
            # -- PlmXml changed, re-initialize by loading plmxml --
            self._update_status(_('PlmXml weicht von vorhergehend geschalteter PlmXml ab. '
                                  'AsConnector muss re-initialisiert werden. Dies dauert einen Moment.')
                                + f' <i>{KnechtSettings.app.get("last_plmxml") or plmxml_file.name}</i>')
        else:
            # -- Scene changed, re-initialize by loading plmxml --
            self._update_status(_('Aktive DeltaGen Szene weicht von vorhergehend geschalteter Szene ab. '
                                  'AsConnector muss re-initialisiert werden. Dies dauert einen Moment.')
                                + f' <i>{KnechtSettings.app.get("last_scene") or active_scene}</i>')

        # -- Load PlmXml as DeltaGen Scene --
        load_request = AsSceneLoadPlmXmlRequest(plmxml_file)
        load_response = self.as_conn.request(load_request, retry=False)

        if not load_response:
            self._update_status(_('Konnte PlmXml nicht in DeltaGen laden. '
                                  'AsConnector konnte nicht re-initialisiert werdem! Materialschaltungen '
                                  'könnten unter Umständen nicht funktionieren.'))
            return False

        # -- Close the loaded PlmXml --
        sleep(0.3)
        close_request = AsSceneCloseRequest(plmxml_file.name)
        close_result = self.as_conn.request(close_request)

        if not close_result:
            self._update_status(_('Konnte geladene PlmXml nicht schliessen. '
                                  'AsConnector konnte vermutlich re-initialisiert werden. '
                                  'Die geladene PlmXml Szene kann geschlossen werden.'))
            return False

        self._update_status(_('AsConnector erfolgreich re-initialisiert.'))
        KnechtSettings.app['last_plmxml'] = plmxml_file.name
        KnechtSettings.app['last_scene'] = active_scene
        return True


def create_pr_string_from_variants(variants_ls: KnechtVariantList) -> str:
    pr_conf = ''

    for variant in variants_ls.variants:
        pr_conf += f'+{variant.name}'

    return pr_conf
