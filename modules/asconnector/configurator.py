import re
from typing import Tuple, List, Set, Dict

from plmxml import PlmXml
from plmxml.objects import NodeInfo, MaterialTarget
from plmxml.utils import pr_tags_to_reg_ex

from modules.language import get_translation
from modules.log import init_logging
from modules.asconnector.connector import AsConnectorConnection
from modules.asconnector.request import AsNodeSetVisibleRequest, AsMaterialConnectToTargetsRequest, \
    AsSceneGetStructureRequest, AsTargetGetAllNamesRequest

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class PlmXmlConfigurator:
    def __init__(self, plmxml: PlmXml, config: str):
        """ Parses a configuration String against an initialized PlmXml instance and edits the
            product instances and materials that need their visibility or source looks changed.

        :param PlmXml plmxml: PlmXml instance holding info about look library and product instances
        :param str config: Configuration String
        """
        self.plmxml = plmxml
        self.config = config
        self.errors = list()

        self.status_msg = str()

        self._valid_targets: List[MaterialTarget] = list()
        self._missing_targets: List[MaterialTarget] = list()

        # Parse PlmXml against config on initialisation
        self._parse_plmxml_against_config()

    def update_config(self, config: str):
        self.config = config
        self._parse_plmxml_against_config()

    def _update_plmxml_with_as_connector_nodes(self, scene_get_structure_result_nodes: Dict[str, NodeInfo]):
        idx = 0
        for node in self.plmxml.iterate_configurable_nodes():
            if node.knecht_id in scene_get_structure_result_nodes:
                node.as_id = scene_get_structure_result_nodes.get(node.knecht_id).as_id
                idx += 1

        LOGGER.debug('Updated AsConnector Scene Ids of %s PlmXml Nodes', idx)

    def validate_scene_vs_plmxml(self) -> Tuple[bool, List[NodeInfo], Set[str]]:
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
        as_conn = AsConnectorConnection()

        # ---- Validate scene structure ----
        # -- Create GetSceneStructureRequest
        root_node_dummy = NodeInfo(as_id='root', parent_node_id='root')
        scene_request = AsSceneGetStructureRequest(root_node_dummy, list())
        request_result = as_conn.request(scene_request)

        if not request_result:
            # Request failed
            return False, missing_nodes, missing_target_names

        # -- Update As Connector Id's
        self._update_plmxml_with_as_connector_nodes(scene_request.result)

        for node in self.plmxml.iterate_configurable_nodes():
            if node.knecht_id not in scene_request.result:
                missing_nodes.append(node)

        # -- Get Invalid Material Targets
        _, missing_targets = self._get_valid_material_targets()
        missing_target_names = {t.name for t in missing_targets if t.name}

        LOGGER.debug('Validate Scene vs PlmXml Result: %s nodes are missing. '
                     '%s Material Targets are missing or unloaded.', len(missing_nodes), len(missing_target_names))

        # Request successful, missing LincId's
        return True, missing_nodes, missing_target_names

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

        as_conn = AsConnectorConnection()
        if not as_conn.check_connection():
            return list(), list()

        # ---- Get Scene Materials ----
        get_material_names_req = AsTargetGetAllNamesRequest()
        result = as_conn.request(get_material_names_req)
        valid_targets, missing_targets = list(), list()

        if result:
            for target in self.plmxml.look_lib.iterate_active_targets():
                if target.name not in get_material_names_req.result:
                    missing_targets.append(target)
                else:
                    valid_targets.append(target)

        return valid_targets, missing_targets

    def request_delta_gen_update(self) -> bool:
        """ Send requests to AsConnector2 to update the DeltaGen scene with the current configuration

        :return:
        """
        as_conn, result = AsConnectorConnection(), True

        # Check Connection
        if not as_conn.check_connection():
            self.errors.append(as_conn.error)
            return False

        # -- Update Scene Objects Visibility
        for visibility_request in self.create_visibility_requests():
            req_result = as_conn.request(visibility_request)

            # Handle failed requests
            if not req_result:
                result = False
                self.errors.append(as_conn.error)
                LOGGER.debug('%s', as_conn.error)

        # -- Update Materials
        req_result = as_conn.request(self.create_material_connect_to_targets_request())

        if not req_result or not result:
            self.errors.append(as_conn.error)
            LOGGER.debug('%s', as_conn.error)
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

    def create_material_connect_to_targets_request(self) -> AsMaterialConnectToTargetsRequest:
        valid_material_targets, invalid_material_targets = self._get_valid_material_targets()

        # --- Report Missing Material Targets ---
        if invalid_material_targets:
            self.status_msg += '\n\n'
            self.status_msg += _('Die Szene enthält ungeladene/fehlende Material Targets:')
            self.status_msg += f'\n{"; ".join([m.name for m in invalid_material_targets])}\n'
            self.status_msg += _('Diese wurden bei der Konfiguration ignoriert.')

        return AsMaterialConnectToTargetsRequest(valid_material_targets)

    def _match(self, pr_tags) -> bool:
        """ Match a PR Tag against the current configuration string """
        m = re.match(pr_tags_to_reg_ex(pr_tags), self.config, flags=re.IGNORECASE)

        if m:
            return True

        return False

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

    def _parse_plmxml_against_config(self):
        # -- Geometry
        # -- Set Visibility of Parts with PR_TAGS
        for n in self.plmxml.iterate_configurable_nodes():
            # Match PR TAGS against configuration
            if self._match(n.pr_tags):
                n.visible = True
            else:
                n.visible = False

        # -- Materials
        self._update_plmxml_look_library()

        # -- Print result
        self._set_status_msg()

    def _update_plmxml_look_library(self):
        # -- Materials
        # -- Reset visible variants
        self.plmxml.look_lib.reset()

        # -- Assign Source to Target materials
        for target, variant in self.plmxml.look_lib.iterate_materials():
            if not variant.pr_tags:
                continue

            # Match material PR TAGS against configuration
            if self._match(variant.pr_tags):
                target.visible_variant = variant

                if self.plmxml.debug:
                    LOGGER.debug(f'Switching Material {target.name[:40]:40} -> {variant.name}')
