from typing import Iterator, List, Union

from lxml import etree as Et
from requests import Response

from modules.language import get_translation
from modules.plmxml.objects import MaterialTarget, NodeInfo, ProductInstance
from modules.plmxml.globals import AS_CONNECTOR_IP, AS_CONNECTOR_PORT, AS_CONNECTOR_API_URL, PLM_XML_NAMESPACE
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

    xmlns = "urn:authoringsystem_v2"
    xsd = "http://www.w3.org/2001/XMLSchema"
    xsi = "http://www.w3.org/2001/XMLSchema-instance"

    ns_map = {'xsd': xsd, 'xsi': xsi, None: xmlns}

    base_url = f'http://{AS_CONNECTOR_IP}:{AS_CONNECTOR_PORT}/{AS_CONNECTOR_API_URL}///'
    base_header = {'Content-Type': 'application/xml', 'Host': f'http://{AS_CONNECTOR_IP}:{AS_CONNECTOR_PORT}'}

    def __init__(self):
        self._request = None
        self.url = ''
        self.error = str()

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
        if not xml:
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
        try:
            e = self._response_to_element(r)
        except Exception as err:
            LOGGER.error('Error reading AsConnector response: %s', err)
            self.error = str(err)
            return False

        if r.ok:
            LOGGER.debug('AsConnector response to %s was OK.\n%s', self.__class__.__name__, r.text)
            return self._read_response(e)
        else:
            LOGGER.error('Error while sending request:\n%s', self.to_string())
            LOGGER.error('AsConnector result:\n%s', r.text)
            return self._read_error_response(e)

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

    def _read_error_response(self, r_xml: Et._Element) -> bool:
        self.error = f'Error while sending {self.__class__.__name__} request.\nAsConnector returned:\n' \
                     f'{self.to_string(r_xml)}'
        return False


class AsMaterialConnectToTargetsRequest(AsConnectorRequest):
    response_xpath = f'{{{AsConnectorRequest.xmlns}}}returnVal'

    def __init__(self,
                 target_materials: Union[Iterator, List[MaterialTarget]],
                 use_copy_method: bool=False,
                 replace_target_name: bool=False
                 ):
        """ Create a Material:ConnectToTarget Request

            <?xml version="1.0" encoding="utf-8"?>
            <MaterialConnectToTargetsRequest xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns="urn:authoringsystem_v2">
                <materialNames>
                    <string>
                        ABC001
                    </string>
                </materialNames>
                <targetNames>
                    <string>
                        E_ABC000_Default
                    </string>
                </targetNames>
                <useCopyMethod>
                    false
                </useCopyMethod>
                <replaceTargetName>
                    false
                </replaceTargetName>
            </MaterialConnectToTargetsRequest>

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

        return result


class AsNodeSetVisibleRequest(AsConnectorRequest):
    response_xpath = f'{{{AsConnectorRequest.xmlns}}}returnVal'

    def __init__(self, product_instances: Union[List[ProductInstance], Iterator], visible=False):
        super(AsNodeSetVisibleRequest, self).__init__()
        self.url = f'node/set/visible'
        self._expected_result = 'true' if visible else 'false'

        self._set_request(product_instances, visible)

    def _set_request(self, product_instances: Union[List[ProductInstance], Iterator], visible: bool):
        e = self._create_request_root_element('Node', 'SetVisible')
        nodes = Et.SubElement(e, 'nodes')

        for p in product_instances:
            # Create Node Info object
            node_info = NodeInfo(p)
            # Append NodeInfo Xml element to nodes
            nodes.append(node_info.element)

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
    response_xpath = f'{{{AsConnectorRequest.xmlns}}}returnVal'

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
