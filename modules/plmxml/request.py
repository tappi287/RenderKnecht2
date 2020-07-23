from pathlib import Path, WindowsPath
from typing import Iterator, List, Union, Dict

from lxml import etree as Et
from requests import Response

from modules.language import get_translation
from modules.log import init_logging
from modules.plmxml.globals import PlmXmlGlobals as Pg
from modules.plmxml.objects import MaterialTarget, NodeInfo, NodeInfoTypes

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class AsConnectorRequest:
    """ Create Requests to the AsConnector REST Api2 and handle the response

        DeltaGen Port: 1234
        url: http://127.0.0.1:1234/v2///<METHOD-TYPE>/[GET/SET/]<METHOD>
        eg.: http://127.0.0.1:1234/v2///material/connecttotargets

        request:
        <?xml version="1.0" encoding="utf-8"?>
        <{method_type}{method_camel_case}Request xmlns:xsd="http://www.w3.org/2001/XMLSchema"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns="urn:authoringsystem_v2">
            <{parameter}>
                {value}
            </{parameter}>
        </{method_type}{method_camel_case}Request>
    """
    
    xsd = "http://www.w3.org/2001/XMLSchema"
    xsi = "http://www.w3.org/2001/XMLSchema-instance"
    
    ns_map = {'xsd': xsd, 'xsi': xsi, None: Pg.AS_CONNECTOR_NS}
    
    base_url = f'http://{Pg.AS_CONNECTOR_IP}:{Pg.AS_CONNECTOR_PORT}' \
               f'/{Pg.AS_CONNECTOR_API_URL}///'
    base_header = {'Content-Type': 'application/xml', 'Host': f'http://{Pg.AS_CONNECTOR_IP}:{Pg.AS_CONNECTOR_PORT}'}

    def __init__(self):
        self._request = None
        self.url = ''
        self.error = _('Kein Fehler definiert.')

    @property
    def request(self):
        return self._request

    @request.setter
    def request(self, value: Et._Element):
        self._request = value

    def get_url(self):
        return f'{self.base_url}{self.url}'

    def get_header(self) -> dict:
        header = dict()
        header.update(self.base_header)
        # Will be set by requests library!?
        # header['Content-Length'] = str(len(self.request_to_bytes()))
        return header

    def to_string(self, xml: Union[None, Et._Element]=None) -> str:
        if xml is None:
            xml = self.request

        return Et.tostring(xml,
                           xml_declaration=True,
                           encoding="utf-8",
                           pretty_print=True).decode('utf-8')

    def to_bytes(self) -> bytes:
        return Et.tostring(self.request, xml_declaration=True, encoding="utf-8", pretty_print=False)

    def _create_request_root_element(self, method_type, method_name) -> Et._Element:
        """ Create the request root node

            {method_type}{method_camel_case}Request {namespace}

            ->

            <TypeMethodNameRequest xmlns:xsd="http://www.w3.org/2001/XMLSchema"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns="urn:authoringsystem_v2">

        :param str method_type:
        :param str method_name:
        :return:
        """
        return Et.Element(f'{method_type}{method_name}Request', nsmap=self.ns_map)

    def handle_response(self, r: Response) -> bool:
        """ Handle the AsConnector http respsonse """
        e = None
        try:
            e = self._response_to_element(r)
        except Exception as err:
            LOGGER.error('%s could not read AsConnector response as xml: %s', self.__class__.__name__, err)
            self.error = _('{} konnte AsConnector Antwort nicht interpretieren: {}'
                           ).format(self.__class__.__name__, str(err))

        if r.ok and e is not None:
            text = 'XML Response too huge to print.'
            if len(r.text) < 2000:
                text = r.text

            LOGGER.debug('AsConnector response to %s was OK.\n%s', self.__class__.__name__, text)
            return self._read_response(e)
        else:
            LOGGER.error('Error while sending request to %s:\n%s', self.get_url(), self.to_string())
            LOGGER.error('AsConnector result:\n%s', r.text)
            return self._read_error_response(r)

    @staticmethod
    def _response_to_element(r: Response) -> Et._Element:
        request_string = r.text
        if not request_string.startswith("<"):
            request_string = request_string[request_string.find("<"):len(request_string)]

        if not request_string.startswith("<") or not request_string:
            return Et.Element('None')

        return Et.fromstring(request_string.encode('utf-8'))

    def _read_response(self, r_xml: Et._Element) -> bool:
        """ Read the response Xml in individual requests sub classes """
        LOGGER.debug(f'The {self.__class__.__name__} has not implemented a method to analyse the AsConnector response.'
                     f'Xml Content of response was:\n{self.to_string(r_xml)}')
        return True

    def _read_error_response(self, r: Response) -> bool:
        self.error = _('Fehler beim senden von {} Anfrage.\nAsConnector antwortete:\n{}').format(
                       self.__class__.__name__, r.text[:500]
                       )
        return False


class AsMaterialConnectToTargetsRequest(AsConnectorRequest):
    response_xpath = f'{Pg.AS_CONNECTOR_XMLNS}returnVal'

    def __init__(self,
                 target_materials: Union[Iterator, List[MaterialTarget]],
                 use_copy_method: bool=False,
                 replace_target_name: bool=False
                 ):
        """ Create a Material:ConnectToTarget Request

        :param List[MaterialTarget] target_materials:
        :param bool use_copy_method:
        :param bool replace_target_name:
        """
        super(AsMaterialConnectToTargetsRequest, self).__init__()
        self.url = 'material/connecttotargets'

        self._set_request(target_materials, use_copy_method, replace_target_name)

    def _set_request(self,
                     target_materials: Union[Iterator, List[MaterialTarget]],
                     use_copy_method: bool,
                     replace_target_name: bool
                     ):
        e = self._create_request_root_element('Material', 'ConnectToTargets')
        material_names_parent = Et.SubElement(e, 'materialNames')
        target_names_parent = Et.SubElement(e, 'targetNames')

        # -- Add source materials and their corresponding targets
        for target in target_materials:
            material_node = Et.SubElement(material_names_parent, 'string')
            material_node.text = target.visible_variant.name
            target_node = Et.SubElement(target_names_parent, 'string')
            target_node.text = target.name

        # -- Add additional parameters
        for tag, value in [('useCopyMethod', use_copy_method), ('replaceTargetName', replace_target_name)]:
            param_node = Et.SubElement(e, tag)
            param_node.text = 'true' if value else 'false'

        self.request = e

    def _read_response(self, r_xml: Et._Element) -> bool:
        result = True

        for e in r_xml.iterfind(self.response_xpath):
            if e.text != 'true':
                result = False

        if result:
            LOGGER.debug('AsConnector successfully updated requested Materials.')
        else:
            LOGGER.error('AsConnector update material request failed!')
            self.error = _('Fehler beim senden von {} Anfrage.\nAsConnector konnte Materialien nicht '
                           'aktualisieren.').format(self.__class__.__name__)

        return result


class AsNodeSetVisibleRequest(AsConnectorRequest):
    response_xpath = f'{Pg.AS_CONNECTOR_XMLNS}returnVal'

    def __init__(self, nodes: Union[List[NodeInfo], Iterator], visible=False):
        super(AsNodeSetVisibleRequest, self).__init__()
        self.url = f'node/set/visible'
        self._expected_result = 'true' if visible else 'false'
        self._set_request(nodes, visible)

    def _set_request(self, nodes: Union[List[NodeInfo], Iterator[NodeInfo]], visible: bool):
        e = self._create_request_root_element('Node', 'SetVisible')
        n = Et.SubElement(e, 'nodes')

        for p in nodes:
            # Append NodeInfo Xml element to nodes
            n.append(p.element)

        # -- Add visible parameter
        node_vis = Et.SubElement(e, 'visible')
        node_vis.text = 'true' if visible else 'false'

        self.request = e

    def _read_response(self, r_xml: Et._Element) -> bool:
        result = True

        for e in r_xml.iterfind(self.response_xpath):
            if e.text != self._expected_result:
                result = False

        if result:
            LOGGER.debug('AsConnector successfully updated visibility of requested Product instances.')

        return result


class AsGetVersionInfoRequest(AsConnectorRequest):
    response_xpath = f'{Pg.AS_CONNECTOR_XMLNS}returnVal'

    def __init__(self):
        """ Create a Version Info request

            <?xml version="1.0" encoding="utf-8"?>
            <GetVersionInfoRequest xmlns:xsd="http://www.w3.org/2001/XMLSchema"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns="urn:authoringsystem_v2" />

        """
        super(AsGetVersionInfoRequest, self).__init__()
        self.url = 'getversioninfo'
        self.result = str()
        self._set_request()

    def _set_request(self):
        e = self._create_request_root_element('GetVersionInfo', '')
        self.request = e

    def _read_response(self, r_xml: Et._Element) -> bool:
        result = True

        for e in r_xml.iterfind(self.response_xpath):
            if e.text[0].isdigit():
                self.result = e.text
            else:
                result = False

        if result:
            LOGGER.debug('AsConnector VersionInfo request successful. Found version %s', self.result)

        return result


class AsNodeGetSelection(AsConnectorRequest):
    response_xpath = f'{Pg.AS_CONNECTOR_XMLNS}returnVal/'
    
    def __init__(self):
        super(AsNodeGetSelection, self).__init__()
        self.url = 'node/get/selection'
        self.result = str()
        self._set_request()

    def _set_request(self):
        e = self._create_request_root_element('Node', 'GetSelection')
        self.request = e

    def _read_response(self, r_xml: Et._Element) -> bool:
        e = r_xml.find(self.response_xpath)

        if e is not None:
            self.result = NodeInfo.get_node_from_as_connector_element(e)
            return True
        else:
            return False


class AsGetSelectedNodeEventRequest(AsConnectorRequest):
    response_xpath = f'{Pg.AS_CONNECTOR_XMLNS}returnVal/'

    def __init__(self):
        """ GetSelectedNodeEventRequest """
        super(AsGetSelectedNodeEventRequest, self).__init__()
        self.url = 'event/selected'
        self._set_request()

    def _set_request(self):
        e = self._create_request_root_element('GetSelectedNode', 'Event')
        self.request = e

    def _read_response(self, r_xml: Et._Element) -> bool:
        e = r_xml.find(self.response_xpath)

        if e is not None:
            return True
        else:
            return False


class AsSceneGetStructureRequest(AsConnectorRequest):
    response_xpath = f'{Pg.AS_CONNECTOR_XMLNS}returnVal/'
    deep_response_xpath = f'{Pg.AS_CONNECTOR_XMLNS}returnVal//'

    def __init__(self, start_node: NodeInfo, types: List[str]=None):
        """ Get all child nodes from given startNode, use as_id=root, parent_node_id=root for the complete scene

        :param start_node: The root node to start the search from.
        :param types: The list of node types that shall be returned.
        :returns: The child nodes of startNode that match the given types.
        """
        super(AsSceneGetStructureRequest, self).__init__()
        self.url = 'scene/get/structure'
        self.result: Dict[str, NodeInfo] = dict()

        self._set_request(start_node, types or list())

    def _set_request(self, start_node: NodeInfo, types: List[str]):
        if types is None:
            # Default setting
            types = ['GROUP', 'FILE']
        else:
            invalid_types = [t for t in types if t not in NodeInfoTypes.enumerations]

            for t in invalid_types:
                LOGGER.error('%s requested with invalid type: %s', self.__class__.__name__, t)
                types.remove(t)

        # <SceneGetStructureRequest>
        e = self._create_request_root_element('Scene', 'GetStructure')

        # -<node>
        n = Et.SubElement(e, 'node')
        # --<NodeInfo>
        n.append(start_node.element)
        # --</NodeInfo>
        # -</node>

        # -<types>
        types_element = Et.SubElement(e, 'types')

        for t in types:
            # --<NodeInfoType>
            nt = Et.SubElement(types_element, 'NodeInfoType')
            nt.text = t
            # --</NodeInfoType>
        # -</types>

        # </SceneGetStructureRequest>
        self.request = e

    def _read_response(self, r_xml: Et._Element) -> bool:
        if r_xml is None:
            return False

        for n in r_xml.iterfind(self.response_xpath):
            node = NodeInfo.get_node_from_as_connector_element(n)
            self.result[node.knecht_id or node.as_id] = node

        return True


class AsSceneLoadRequest(AsConnectorRequest):
    response_xpath = f'{Pg.AS_CONNECTOR_XMLNS}returnVal'

    def __init__(self, scene_path: Path, close_active_sessions: bool = False, load_assemblies: bool = False):
        """ Load a Scene with AsConnector
        :returns: The name of the active scene as string
        :rtype: str
        """
        super(AsSceneLoadRequest, self).__init__()
        self.url = 'scene/load'

        self.result = str()
        self.expected_result = 'true'
        self.scene_path = scene_path

        self._set_request(close_active_sessions, load_assemblies)

    def _set_request(self, close_active_sessions, load_assemblies):
        e = self._create_request_root_element('Scene', 'Load')
        self.request = e

        # -<path>
        n = Et.SubElement(e, 'path')
        n.text = str(WindowsPath(self.scene_path))

        # -closeActiveSessions>
        c = Et.SubElement(e, 'closeActiveSessions')
        c.text = str(close_active_sessions).lower()

        # -<loadAssemblies>
        l = Et.SubElement(e, 'loadAssemblies')
        l.text = str(load_assemblies).lower()

        self.request = e

    def _read_response(self, r_xml: Et._Element) -> bool:
        result = False

        for e in r_xml.iterfind(self.response_xpath):
            if e.text:
                self.result = e.text
                if self.result == self.expected_result:
                    result = True

        if result:
            LOGGER.debug('AsConnector SceneLoad request successful: %s', self.result)

        return result


class AsSceneGetActiveRequest(AsConnectorRequest):
    response_xpath = f'{Pg.AS_CONNECTOR_XMLNS}returnVal'

    def __init__(self):
        """ Get the name of the currently active scene.
        :returns: The name of the active scene as string
        :rtype: str
        """
        super(AsSceneGetActiveRequest, self).__init__()
        self.url = 'scene/get/active'

        self.result = str()
        self._set_request()

    def _set_request(self):
        e = self._create_request_root_element('Scene', 'GetActive')
        self.request = e

    def _read_response(self, r_xml: Et._Element) -> bool:
        result = False

        for e in r_xml.iterfind(self.response_xpath):
            if e.text:
                result = True
                self.result = e.text

        if result:
            LOGGER.debug('AsConnector SceneGetActive request successful. Found scene %s', self.result)

        return result


class AsSceneGetAllRequest(AsConnectorRequest):
    response_xpath = f'{Pg.AS_CONNECTOR_XMLNS}returnVal/{Pg.AS_CONNECTOR_XMLNS}Scene/{Pg.AS_CONNECTOR_XMLNS}Name'

    def __init__(self):
        """ Returns a list of all scene names.

        :returns: List[str] Retrieve all scenes from the authoring system.
        """
        super(AsSceneGetAllRequest, self).__init__()
        self.url = 'scene/get/all'

        self.result: List[str] = list()
        self._set_request()

    def _set_request(self):
        e = self._create_request_root_element('Scene', 'GetAll')
        self.request = e

    def _read_response(self, r_xml: Et._Element) -> bool:
        result = False
        self.result: List[str] = list()

        for e in r_xml.iterfind(self.response_xpath):
            if e.text:
                result = True
                self.result.append(e.text)

        if result:
            LOGGER.debug('AsConnector SceneGetAll request successful. Found scenes %s', self.result)

        return result


class AsSceneSetActiveRequest(AsConnectorRequest):
    response_xpath = f'{Pg.AS_CONNECTOR_XMLNS}returnVal'

    def __init__(self, scene_name: str):
        """ Request the scene with name: <scene_name> to be set active.

        :param str scene_name: The name of the scene to set active
        :returns: bool true if successfully set
        :rtype: bool
        """
        super(AsSceneSetActiveRequest, self).__init__()
        self.url = 'scene/set/active'
        self._set_request(scene_name)

    def _set_request(self, scene_name: str):
        e = self._create_request_root_element('Scene', 'SetActive')
        n = Et.SubElement(e, 'name')
        m = Et.SubElement(n, 'string')
        m.text = scene_name

        self.request = e

    def _read_response(self, r_xml: Et._Element) -> bool:
        result = True

        for e in r_xml.iterfind(self.response_xpath):
            if e.text != 'true':
                result = False

        if result:
            LOGGER.debug('AsConnector successfully set active scene.')

        return result


class AsTargetGetAllNamesRequest(AsConnectorRequest):
    response_xpath = f'{Pg.AS_CONNECTOR_XMLNS}returnVal/'

    def __init__(self):
        """ Retrieve the names of all targets in the scene.

        Result: The list with all target names.
        ResultType: List[str]
        """
        super(AsTargetGetAllNamesRequest, self).__init__()
        self.url = 'material/getallnames'
        self._set_request()

    def _set_request(self, ):
        e = self._create_request_root_element('Target', 'GetAllNames')
        self.request = e

    def _read_response(self, r_xml: Et._Element) -> bool:
        result = True
        self.result = list()

        for e in r_xml.iterfind(self.response_xpath):
            if e.text:
                self.result.append(e.text)

        if self.result:
            result = True
            LOGGER.debug('AsConnector successfully got all material names from scene.')

        return result
