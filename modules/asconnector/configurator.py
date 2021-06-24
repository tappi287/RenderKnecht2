from typing import Tuple, List, Set, Dict, Optional

from plmxml import PlmXml
from plmxml.configurator import PlmXmlBaseConfigurator
from plmxml.material import MaterialTarget, MaterialVariant
from plmxml.node_info import NodeInfo

from modules import KnechtSettings
from modules.asconnector.connector import AsConnectorConnection
from modules.asconnector.request import AsNodeSetVisibleRequest, AsMaterialConnectToTargetsRequest, \
    AsSceneGetStructureRequest, AsTargetGetAllNamesRequest, AsNodeDeleteRequest, AsMaterialDeleteRequest
from modules.globals import CSB_DUMMY_MATERIAL
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class PlmXmlConfigurator(PlmXmlBaseConfigurator):
    def __init__(self, plmxml: PlmXml, config: str, as_conn: AsConnectorConnection = None,
                 status_update: Optional[callable] = None):
        """ Parses a configuration String against an initialized PlmXml instance and edits the
            product instances and materials that need their visibility or source looks changed.

        :param PlmXml plmxml: PlmXml instance holding info about look library and product instances
        :param str config: Configuration String
        :param AsConnectorConnection as_conn:
        :param callable status_update: method to post direct status update messages to
        """
        super(PlmXmlConfigurator, self).__init__(plmxml, config)
        self.plmxml = plmxml
        self.config = config
        self.as_conn = as_conn or AsConnectorConnection()
        self.errors = list()

        self.status_msg = str()
        self.status_update_method = status_update

        self._valid_targets: List[MaterialTarget] = list()
        self._missing_targets: List[MaterialTarget] = list()

        # Parse PlmXml against config on initialisation
        self._setup_plmxml_product_instances()

    def _update_status_message(self, message: str):
        if self.status_update_method:
            self.status_update_method(message)

    def update_config(self, config: str):
        self.config = config
        self._setup_plmxml_product_instances()

    def _setup_plmxml_product_instances(self):
        """ Request plmxml instance update from BaseConfigurator.
            This will update visibility of ProductInstances and visible_variants of LookLibrary Materials.
        """
        self.update()

        # -- Print result
        self._set_status_msg()

    def _update_plmxml_with_as_connector_nodes(self, scene_get_structure_result_nodes: Dict[str, NodeInfo]):
        idx = 0
        for node in self.plmxml.iterate_configurable_nodes():
            if node.knecht_id in scene_get_structure_result_nodes:
                node.as_id = scene_get_structure_result_nodes.get(node.knecht_id).as_id
                idx += 1

        LOGGER.debug('Updated AsConnector Scene Ids of %s PlmXml Nodes', idx)

    def validate_scene_vs_plmxml(self) -> Tuple[bool, List[NodeInfo], Set[str], Optional[NodeInfo]]:
        """ Validate the currently loaded Scene versus
            the PlmXml. Report missing Nodes/Parts and missing material targets.

            Return as invalid if missing Nodes encountered. Missing targets can
            occur due to unloaded parts and will not set status to invalid.

            Note:
             If scene was saved with "Save Structure as..", DeltaGen will also
             save the scene materials regardless of loaded assemblies.
             There could be target materials in the scene that are not bound to any meshes.
             Therefore they will not be reported but still be invalid.

        :return: Request was un/-successful, List of missing nodes, set of missing/unloaded target materials
        :rtype: bool, List[NodeInfo], Set[str]
        """
        missing_nodes: List[NodeInfo] = list()
        missing_target_names: Set[str] = set()
        material_dummy: Optional[NodeInfo] = None

        # ---- Validate scene structure ----
        # -- Create GetSceneStructureRequest
        root_node_dummy = NodeInfo(as_id='root', parent_node_id='root')
        scene_request = AsSceneGetStructureRequest(root_node_dummy, list())
        request_result = self.as_conn.request(scene_request)

        if not request_result:
            # Request failed
            return False, missing_nodes, missing_target_names, material_dummy

        # -- Update As Connector Id's
        self._update_plmxml_with_as_connector_nodes(scene_request.result)

        # -- Check for Material Dummy *.csb Group or Material
        for _id, node in scene_request.result.items():
            if node.name == CSB_DUMMY_MATERIAL and node.type == 'GROUP':
                material_dummy = node

        # -- Compare PlmXml vs Scene
        for node in self.plmxml.iterate_configurable_nodes():
            if node.knecht_id not in scene_request.result:
                missing_nodes.append(node)

        # -- Get Invalid Material Targets
        _, missing_targets = self._get_valid_material_targets()
        missing_target_names = {t.name for t in missing_targets if t.name}

        LOGGER.debug('Validate Scene vs PlmXml Result: %s nodes are missing. '
                     '%s Material Targets are missing or unloaded.', len(missing_nodes), len(missing_target_names))

        # Request successful, missing LincId's
        return True, missing_nodes, missing_target_names, material_dummy

    def request_delta_gen_update(self) -> bool:
        """ Send requests to AsConnector2 to update the DeltaGen scene with the current configuration """
        result = True

        # -- Update Scene Objects Visibility
        for visibility_request in self.create_visibility_requests():
            req_result = self.as_conn.request(visibility_request)

            # Handle failed requests
            if not req_result:
                result = False
                self.errors.append(self.as_conn.error)
                LOGGER.debug('%s', self.as_conn.error)

        self._update_status_message(_('Sichtbarkeit der Szenenobjekte aktualisiert ...'))

        # -- Assign Dummy Material to all Targets if Setting active
        self._assign_dummy_material()

        # -- Update Materials
        self._update_status_message(_('Starte Materialzuweisung für angefragte Konfiguration ...'))
        req_result = self.as_conn.request(self.create_material_connect_to_targets_request())

        # -- Invalidate cached Materials
        self._valid_targets, self._missing_targets = list(), list()

        if not req_result or not result:
            self.errors.append(self.as_conn.error)
            LOGGER.debug('%s', self.as_conn.error)
            return False

        return True

    def create_visibility_requests(self) -> Tuple[AsNodeSetVisibleRequest, AsNodeSetVisibleRequest]:
        # -- Set Visibility of Geometry
        visible_nodes, invisible_nodes = list(), list()

        for p in self.plmxml.iterate_configurable_nodes():
            if p.visible:
                visible_nodes.append(p)
            elif not p.visible:
                invisible_nodes.append(p)

        # -- Create the actual NodeSetVisibleRequest objects
        invisible_request = AsNodeSetVisibleRequest(invisible_nodes, False)
        visible_request = AsNodeSetVisibleRequest(visible_nodes, True)

        return visible_request, invisible_request

    def _assign_dummy_material(self):
        """ Assign a dummy Material to every Target Material """
        if not KnechtSettings.dg.get('use_material_dummy'):
            return

        self._update_status_message(_('Wende Dummy Material auf Target Materialien an'))
        dummy_targets = list()
        dummy_variant = MaterialVariant(CSB_DUMMY_MATERIAL.replace('.csb', ''), '', '')

        LOGGER.info('Assigning Material Dummy to PlmXml Scene %s', CSB_DUMMY_MATERIAL.replace('.csb', ''))

        for target, _m in self.plmxml.look_lib.iterate_materials():
            _dummy_target = MaterialTarget(target.name, [dummy_variant])
            _dummy_target.visible_variant = dummy_variant
            dummy_targets.append(_dummy_target)

        # -- Actually assign the Materials
        if not self.as_conn.request(self.create_material_connect_to_targets_request(dummy_targets), retry=False):
            LOGGER.debug('Dummy Assignment failed, trying to re-initialize AsConnector')
            # -- Re-initialize AsConnector if Material Assignment fails
            self.as_conn.initialize_as_connector(self.plmxml.file)
            if not self.as_conn.request(self.create_material_connect_to_targets_request(dummy_targets), retry=False):
                LOGGER.error('Dummy Assignment failed!')
                self._update_status_message(_('Konnte DUMMY Material nicht anwenden: ') + self.as_conn.error)

    def _get_valid_material_targets(self) -> Tuple[List[MaterialTarget], List[MaterialTarget]]:
        """ This will acquire the materials from the scene and compare it to
            the list of active target materials in the PlmXml.

            --- Important ---
            This will not find MaterialTargets with mismatching names!
            Eg. MatTarget and MatTarget_1 will not report an error even though the actual target geometry may has
            the wrong Material MatTarget_1 assigned.

             --- Important!---
             This requires an PlmXml which looklib attribute is
             configured (self._update_plmxml_look_library)! Otherwise no
             active targets can be iterated!

             A more general/independent of configuration validation is done
             in the self.validate_scene_vs_plmxml but can be omitted by the user.
             (Because it takes quite some time)
        """
        if len(self._valid_targets) > 0:
            return self._valid_targets, self._missing_targets

        # ---- Get Scene Materials ----
        get_material_names_req = AsTargetGetAllNamesRequest()
        result = self.as_conn.request(get_material_names_req)
        valid_targets, missing_targets = list(), list()

        if result:
            for target in self.plmxml.look_lib.iterate_active_targets():
                if target.name not in get_material_names_req.result:
                    missing_targets.append(target)
                else:
                    valid_targets.append(target)

        # ---- Cache Result ---
        self._valid_targets, self._missing_targets = valid_targets, missing_targets

        return valid_targets, missing_targets

    def create_material_connect_to_targets_request(self, override_targets: Optional[List[MaterialTarget]] = None) -> AsMaterialConnectToTargetsRequest:
        """ Assign materials in the scene

        :param override_targets:
        :return:
        """
        valid_material_targets, invalid_material_targets = self._get_valid_material_targets()

        if override_targets:
            valid_material_targets = override_targets

        # --- Report Missing Material Targets ---
        if invalid_material_targets and not override_targets:
            self.status_msg += '\n\n'
            self.status_msg += _('Die Szene enthält ungeladene/fehlende Material Targets:')
            self.status_msg += f'\n{"; ".join([m.name for m in invalid_material_targets])}\n'
            self.status_msg += _('Diese wurden bei der Konfiguration ignoriert.')

        LOGGER.info('Assigning materials')
        if self.as_conn.version >= '2.15':
            # New argument useLookUpTable from v2.15
            material_req = AsMaterialConnectToTargetsRequest(valid_material_targets, use_lookup_table=False)
        else:
            material_req = AsMaterialConnectToTargetsRequest(valid_material_targets)

        return material_req

    def _set_status_msg(self):
        self.status_msg += _('Aktualisiere PlmXml Konfiguration. ')
        self.status_msg += f'{len([t for t in self.plmxml.look_lib.iterate_active_targets()])} '
        self.status_msg += _('Materialien zum aktualisieren und ')
        self.status_msg += f'{len([p for p in self.plmxml.iterate_configurable_nodes()])} '
        self.status_msg += _('Objekte zur Änderung der Sichtbarkeit gefunden.')

        not_updated = [t.name for t in self.plmxml.look_lib.materials.values() if not t.visible_variant]
        self.status_msg += '\n'
        self.status_msg += _('Die folgenden {} Materialien erzielten keine Treffer ').format(len(not_updated))
        self.status_msg += _('in der Konfiguration. Sie werden nicht aktualisiert:')
        self.status_msg += f'\n{"; ".join(not_updated)}'
