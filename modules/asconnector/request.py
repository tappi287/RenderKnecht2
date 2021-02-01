from pathlib import Path, WindowsPath
from typing import Iterator, List, Union, Dict, Optional

from lxml import etree as Et
from requests import Response
from plmxml.globals import PlmXmlGlobals as Pg
from plmxml.material import MaterialTarget
from plmxml.node_info import NodeInfo, NodeInfoTypes

from modules.language import get_translation
from modules.log import init_logging

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
    # - Default Response Xpath for string responses like 'true'
    response_xpath = f'{Pg.AS_CONNECTOR_XMLNS}returnVal'

    xsd = "http://www.w3.org/2001/XMLSchema"
    xsi = "http://www.w3.org/2001/XMLSchema-instance"
    
    ns_map = {'xsd': xsd, 'xsi': xsi, None: Pg.AS_CONNECTOR_NS}
    
    base_url = f'http://{Pg.AS_CONNECTOR_IP}:{Pg.AS_CONNECTOR_PORT}' \
               f'/{Pg.AS_CONNECTOR_API_URL}///'
    base_header = {'Content-Type': 'application/xml', 'Host': f'http://{Pg.AS_CONNECTOR_IP}:{Pg.AS_CONNECTOR_PORT}'}

    def __init__(self, url: str = None):
        # - Default expected result to be expected as Xml response content
        self.expected_result = 'true'

        self._request = None

        if url is None:
            LOGGER.warning('AsConnectorRequest subclass: %s did not define request URL!', self.__class__.__name__)
        self.url: str = url or ''
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

        LOGGER.error('Error while sending request to %s:\n%s', self.get_url(), self.to_string())
        LOGGER.error('AsConnector Request result:\n%s', r.text)
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
        e = r_xml.find(self.response_xpath)
        result = True if e is not None and e.text == self.expected_result else False

        if e is None and r_xml is not None:
            LOGGER.debug(
                f'The {self.__class__.__name__} has not implemented a method to analyse the AsConnector response.'
                f'Xml Content of response was:\n{self.to_string(r_xml)}')
            return True

        if result:
            LOGGER.debug('AsConnector %s request successful!', self.__class__.__name__)
        else:
            LOGGER.error('AsConnector %s request failed: %s %s', self.__class__.__name__, e, self.to_string(r_xml))

        return result

    def _read_error_response(self, r: Response) -> bool:
        self.error = _('Fehler beim senden von {} Anfrage.').format(self.__class__.__name__)
        self.error += '\n'
        self.error += _('AsConnector antwortete:')
        self.error += f'\n{r.text[:500]}'
        return False


class AsGetVersionInfoRequest(AsConnectorRequest):
    def __init__(self):
        """ Create a Version Info request

            <?xml version="1.0" encoding="utf-8"?>
            <GetVersionInfoRequest xmlns:xsd="http://www.w3.org/2001/XMLSchema"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns="urn:authoringsystem_v2" />

        """
        super(AsGetVersionInfoRequest, self).__init__('getversioninfo')
        self.result = str()
        self._set_request()

    def _set_request(self):
        self.request = self._create_request_root_element('GetVersionInfo', '')

    def _read_response(self, r_xml: Et._Element) -> bool:
        e = r_xml.find(self.response_xpath)
        if e is not None and e.text[0].isdigit():
            self.result = e.text

        if self.result:
            LOGGER.debug('AsConnector VersionInfo request successful. Found version %s', self.result)

        return True if self.result else False


class AsTargetGetAllNamesRequest(AsConnectorRequest):
    response_xpath = f'{Pg.AS_CONNECTOR_XMLNS}returnVal/'

    def __init__(self):
        """ Retrieve the names of all targets in the scene.

        Result: The list with all target names.
        ResultType: List[str]
        """
        super(AsTargetGetAllNamesRequest, self).__init__('material/getallnames')
        self.result = list()
        self._set_request()

    def _set_request(self, ):
        e = self._create_request_root_element('Target', 'GetAllNames')
        self.request = e

    def _read_response(self, r_xml: Et._Element) -> bool:
        for e in r_xml.iterfind(self.response_xpath):
            if e.text:
                self.result.append(e.text)

        if self.result:
            LOGGER.debug('AsConnector successfully got all material names from scene.')

        return True if self.result else False


class AsMaterialDeleteRequest(AsConnectorRequest):
    """ USELESS AsConnector 2.15 """
    def __init__(self, material_name: str):
        super(AsMaterialDeleteRequest, self).__init__('material/delete')
        self._set_request(material_name)

    def _set_request(self, material_name: str):
        e = self._create_request_root_element('Material', 'Delete')

        # -<materialName>
        n = Et.SubElement(e, 'materialName')
        # --<string>
        s = Et.SubElement(n, 'string')
        s.text = material_name
        # --</string>
        # -</materialName>

        self.request = e


class AsMaterialConnectToTargetsRequest(AsConnectorRequest):
    def __init__(self,
                 target_materials: Union[Iterator, List[MaterialTarget]],
                 use_copy_method: bool=False,
                 replace_target_name: bool=False,
                 use_lookup_table: Optional[bool]=None
                 ):
        """ Create a Material:ConnectToTarget Request

        :param List[MaterialTarget] target_materials:
        :param bool use_copy_method:
        :param bool replace_target_name:
        :param bool use_lookup_table:
        """
        super(AsMaterialConnectToTargetsRequest, self).__init__('material/connecttotargets')
        self._set_request(target_materials, use_copy_method, replace_target_name, use_lookup_table)

    def _set_request(self,
                     target_materials: Union[Iterator, List[MaterialTarget]],
                     use_copy_method: bool,
                     replace_target_name: bool,
                     use_lookup_table: bool
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
        for tag, value in [('useCopyMethod', use_copy_method), ('replaceTargetName', replace_target_name),
                           ('useLookUpTable', use_lookup_table)]:
            if value is not None:
                param_node = Et.SubElement(e, tag)
                param_node.text = 'true' if value else 'false'

        self.request = e


class AsNodeSetVisibleRequest(AsConnectorRequest):
    def __init__(self, nodes: Union[List[NodeInfo], Iterator], visible=False):
        super(AsNodeSetVisibleRequest, self).__init__('node/set/visible')
        self.expected_result = 'true' if visible else 'false'
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


class AsNodeGetSelection(AsConnectorRequest):
    response_xpath = f'{Pg.AS_CONNECTOR_XMLNS}returnVal/'

    def __init__(self):
        super(AsNodeGetSelection, self).__init__('node/get/selection')
        self.result = str()
        self._set_request()

    def _set_request(self):
        e = self._create_request_root_element('Node', 'GetSelection')
        self.request = e

    def _read_response(self, r_xml: Et._Element) -> bool:
        e = r_xml.find(self.response_xpath)

        if e is not None:
            self.result = NodeInfo.get_node_from_as_connector_element(e)
            LOGGER.debug('Node/Get/Selection result: %s', self.result)
            return True
        else:
            return False


class AsNodeAddFilepartRequest(AsConnectorRequest):
    """ USELESS AsConnector 2.15 """
    def __init__(self, node: NodeInfo = None, filepath: Path = Path()):
        super(AsNodeAddFilepartRequest, self).__init__('node/addfilepart')
        self.result = str()
        self.expected_result = 'true'

        node = NodeInfo(node_info_type='FILE') if not node else node
        self._set_request(node, filepath)

    def _set_request(self, node: NodeInfo, filepath: Path):
        e = self._create_request_root_element('Node', 'AddFilepart')

        # -<node>
        n = Et.SubElement(e, 'node')
        # --<NodeInfo>
        n.append(node.element)
        # --</NodeInfo>
        # -</node>

        # -<filepath>
        p = Et.SubElement(e, 'filepath')
        p.text = str(WindowsPath(filepath))
        # -</filepath>

        self.request = e

    def _read_response(self, r_xml: Et._Element) -> bool:
        e = r_xml.find(self.response_xpath)
        result = True if e is not None and e.text == self.expected_result else False

        if result:
            LOGGER.debug('AsConnector AddFilepart request successful: %s', self.result)
        else:
            LOGGER.error('AsConnector AddFilepart request failed: %s %s', e, r_xml)

        return result


class AsNodeDeleteRequest(AsConnectorRequest):
    """ USELESS AsConnector 2.15 """
    def __init__(self, node: NodeInfo = None):
        super(AsNodeDeleteRequest, self).__init__('node/delete')
        self.result = str()
        self.expected_result = 'true'

        node = NodeInfo() if not node else node
        self._set_request(node)

    def _set_request(self, node: NodeInfo):
        e = self._create_request_root_element('Node', 'Delete')

        # -<node>
        n = Et.SubElement(e, 'node')
        # --<NodeInfo>
        n.append(node.element)
        # --</NodeInfo>
        # -</node>

        self.request = e

    def _read_response(self, r_xml: Et._Element) -> bool:
        e = r_xml.find(self.response_xpath)
        result = True if e is not None and e.text == self.expected_result else False

        if result:
            LOGGER.debug('AsConnector Delete request successful: %s\n%s', self.result, self.to_string())
        else:
            LOGGER.error('AsConnector Delete request failed: %s %s', e, r_xml)

        return result


class AsNodeLoadFilepartRequest(AsConnectorRequest):
    """ USELESS AsConnector 2.15 """
    def __init__(self, node: NodeInfo = None, supress_dialogs: bool = True):
        super(AsNodeLoadFilepartRequest, self).__init__('node/loadfilepart')
        self.result = str()
        self.expected_result = 'true'

        node = NodeInfo(node_info_type='FILE') if not node else node

        self._set_request(node, supress_dialogs)

    def _set_request(self, node: NodeInfo, supress_dialogs):
        e = self._create_request_root_element('Node', 'LoadFilepart')

        # -<node>
        n = Et.SubElement(e, 'node')
        # --<NodeInfo>
        n.append(node.element)
        # --</NodeInfo>
        # -</node>

        # -<supressDialogs>
        p = Et.SubElement(e, 'supressDialogs')
        p.text = str(supress_dialogs).lower()
        # -</supressDialogs>

        self.request = e

    def _read_response(self, r_xml: Et._Element) -> bool:
        e = r_xml.find(self.response_xpath)
        result = True if e is not None and e.text == self.expected_result else False

        if result:
            LOGGER.debug('AsConnector LoadFilepart request successful: %s', self.result)
        else:
            LOGGER.error('AsConnector LoadFilepart request failed: %s %s', e, self.to_string())

        return result


class AsNodeCreateRequest(AsConnectorRequest):
    """ USELESS AsConnector 2.15 """
    def __init__(self, parent_node: NodeInfo = None, name: str = '', lincid: str = '',
                 filename: Path = Path(), load_part: bool = False):
        super(AsNodeCreateRequest, self).__init__('node/create')
        self.result: Optional[NodeInfo] = None

        parent_node = NodeInfo(node_info_type='FILE') if not parent_node else parent_node
        self._set_request(parent_node, name, lincid, filename, load_part)

    def _set_request(self, parent_node: NodeInfo, name: str, lincid: str,
                     filename: Path, load_part: bool):
        # <NodeCreateRequest>
        e = self._create_request_root_element('Node', 'Create')

        # -<parentNode>
        n = Et.SubElement(e, 'parentNode')
        # --<NodeInfo>
        n.append(parent_node.element)
        # --</NodeInfo>
        # -</parentNode>

        # -<name>
        ne = Et.SubElement(e, 'name')
        # --<string>
        # m = Et.SubElement(ne, 'string')
        ne.text = name
        # --</string>
        # -</name>

        # -<lincId>
        l = Et.SubElement(e, 'lincId')
        # --<string>
        # s = Et.SubElement(l, 'string')
        l.text = lincid
        # --</string>
        # -</lincId>

        # -<filename>
        p = Et.SubElement(e, 'filename')
        p.text = str(WindowsPath(filename))
        # -</filename>

        # -<loadPart>
        lp = Et.SubElement(e, 'loadPart')
        lp.text = str(load_part).lower()
        # -</loadPart>

        self.request = e

    def _read_response(self, r_xml: Et._Element) -> bool:
        e = r_xml.find(self.response_xpath)

        if e is not None:
            self.result = NodeInfo.get_node_from_as_connector_element(e)
            LOGGER.debug('Node/Create result: %s', self.result)
            return True
        else:
            LOGGER.error('Node Create Request failed: %s', self.to_string())
            return False


class AsGetSelectedNodeEventRequest(AsConnectorRequest):
    response_xpath = f'{Pg.AS_CONNECTOR_XMLNS}returnVal/'

    def __init__(self):
        """ GetSelectedNodeEventRequest """
        super(AsGetSelectedNodeEventRequest, self).__init__('event/selected')
        self.result: Optional[NodeInfo] = None

        self._set_request()

    def _set_request(self):
        e = self._create_request_root_element('GetSelectedNode', 'Event')
        self.request = e

    def _read_response(self, r_xml: Et._Element) -> bool:
        e = r_xml.find(self.response_xpath)
        LOGGER.debug('Event/Selected result: %s', r_xml)

        if e is not None:
            self.result = NodeInfo.get_node_from_as_connector_element(e)
            return True
        else:
            return False


class AsSceneGetStructureRequest(AsConnectorRequest):
    response_xpath = f'{Pg.AS_CONNECTOR_XMLNS}returnVal/'

    def __init__(self, start_node: NodeInfo, types: List[str]=None):
        """ Get all child nodes from given startNode, use as_id=root, parent_node_id=root for the complete scene

        :param start_node: The root node to start the search from.
        :param types: The list of node types that shall be returned.
        :returns: The child nodes of startNode that match the given types.
        """
        super(AsSceneGetStructureRequest, self).__init__('scene/get/structure')
        self.result: Dict[str, NodeInfo] = dict()
        self.scene_root: Optional[Et._Element] = None

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

        self.scene_root = NodeInfo.get_node_from_as_connector_element(r_xml.find(self.response_xpath))

        for idx, n in enumerate(r_xml.iterfind(self.response_xpath)):
            node = NodeInfo.get_node_from_as_connector_element(n)
            node.knecht_id = None if node.knecht_id == 'None' else node.knecht_id
            self.result[node.knecht_id or node.as_id or idx] = node

        return True


class AsSceneLoadRequest(AsConnectorRequest):
    def __init__(self, scene_path: Path, close_active_sessions: bool = False, load_assemblies: bool = False):
        """ Load a Scene with AsConnector

        :param scene_path: The path to the file to load.
        :param close_active_sessions: Specify whether or not to close the currently active session in the AS.
        :param load_assemblies: Specify whether or not to load the connected assemblies.
        :returns: True if the file starts loading.
        :rtype: str
        """
        super(AsSceneLoadRequest, self).__init__('scene/load')
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


class AsSceneLoadPlmXmlRequest(AsSceneLoadRequest):

    def __init__(self, scene_path: Path, close_active_sessions: bool = False, load_assemblies: bool = False,
                 native: bool = False):
        """ Load a Scene with AsConnector

        :param native: If set to false, the authoring system will not use its internal file parser.
                       Instead AsConnector2 parses and builds the scene structure.
                       Only works with PlmXml.
        :returns: True if the file starts loading.
        :rtype: str
        """
        super(AsSceneLoadPlmXmlRequest, self).__init__(scene_path, close_active_sessions, load_assemblies)
        self.scene_path = scene_path

        self._add_request_arg(native)

    def _add_request_arg(self, native):
        # -<native>
        n = Et.SubElement(self.request, 'native')
        n.text = str(native).lower()


class AsSceneCloseRequest(AsConnectorRequest):
    def __init__(self, scene_name: str):
        """ Close the DeltaGen Scene with title scene_name

        :param scene_name: Name of the scene to close
        """
        super(AsSceneCloseRequest, self).__init__('scene/close')
        self.result = str()
        self.expected_result = 'true'
        self._set_request(scene_name)

    def _set_request(self, scene_name):
        e = self._create_request_root_element('Scene', 'Close')
        n = Et.SubElement(e, 'name')
        m = Et.SubElement(n, 'string')
        m.text = scene_name

        self.request = e


class AsSceneGetActiveRequest(AsConnectorRequest):
    def __init__(self):
        """ Get the name of the currently active scene.
        :returns: The name of the active scene as string
        :rtype: str
        """
        super(AsSceneGetActiveRequest, self).__init__('scene/get/active')
        self.result = str()
        self._set_request()

    def _set_request(self):
        e = self._create_request_root_element('Scene', 'GetActive')
        self.request = e

    def _read_response(self, r_xml: Et._Element) -> bool:
        e = r_xml.find(self.response_xpath)
        if e is not None and e.text:
            self.result = e.text
            LOGGER.debug('AsConnector SceneGetActive request successful. Found scene %s', self.result)

        return True if self.result else False


class AsSceneGetAllRequest(AsConnectorRequest):
    response_xpath = f'{Pg.AS_CONNECTOR_XMLNS}returnVal/{Pg.AS_CONNECTOR_XMLNS}Scene/{Pg.AS_CONNECTOR_XMLNS}Name'

    def __init__(self):
        """ Returns a list of all scene names.

        :returns: List[str] Retrieve all scenes from the authoring system.
        """
        super(AsSceneGetAllRequest, self).__init__('scene/get/all')
        self.result: List[str] = list()
        self._set_request()

    def _set_request(self):
        e = self._create_request_root_element('Scene', 'GetAll')
        self.request = e

    def _read_response(self, r_xml: Et._Element) -> bool:
        self.result: List[str] = list()

        for e in r_xml.iterfind(self.response_xpath):
            if e.text:
                self.result.append(e.text)

        if self.result:
            LOGGER.debug('AsConnector SceneGetAll request successful. Found scenes %s', self.result)

        return True if self.result else False


class AsSceneSetActiveRequest(AsConnectorRequest):
    def __init__(self, scene_name: str):
        """ Request the scene with name: <scene_name> to be set active.

        :param str scene_name: The name of the scene to set active
        :returns: bool true if successfully set
        :rtype: bool
        """
        super(AsSceneSetActiveRequest, self).__init__('scene/set/active')
        self._set_request(scene_name)

    def _set_request(self, scene_name: str):
        e = self._create_request_root_element('Scene', 'SetActive')
        n = Et.SubElement(e, 'name')
        m = Et.SubElement(n, 'string')
        m.text = scene_name

        self.request = e
