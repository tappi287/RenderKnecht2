import requests

from modules.plmxml import NodeInfo, ProductInstance, PlmXml
from modules.plmxml.request import AsConnectorRequest, AsGetVersionInfoRequest, AsSceneGetStructureRequest, \
    AsNodeGetSelection
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class AsConnectorConnection:
    timeout = 10

    def __init__(self):
        self._connected = False
        self.error = str()

        self._check_connection()

    @property
    def connected(self):
        return self._connected

    @connected.setter
    def connected(self, value: bool):
        self._connected = value

    def _check_connection(self) -> bool:
        version_request = AsGetVersionInfoRequest()
        result = self.request(version_request)

        if result:
            self.connected = True
            LOGGER.debug(f'Connected to AsConnector {version_request.result}')
        else:
            self.connected = False
            self.error = 'Could not connect to an AsConnector Instance.'

        return result

    def request(self, as_request: AsConnectorRequest) -> bool:
        r, err = None, str()

        try:
            r = requests.post(
                as_request.get_url(), data=as_request.to_bytes(), headers=as_request.get_header(), timeout=10
                )
        except requests.ConnectionError or requests.Timeout or requests.ReadTimeout as e:
            LOGGER.error('Error connecting to AsConnector! %s', e)
            err = str(e)

        if r is not None:
            LOGGER.debug('Sent request to AsConnector, response code was: %s', r.status_code)
            result = as_request.handle_response(r)
            self.error = as_request.error
        else:
            self.error = str(err)
            result = False

        return result
