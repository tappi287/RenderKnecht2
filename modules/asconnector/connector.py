from pathlib import Path
from time import sleep

import requests

from modules.asconnector.request import AsConnectorRequest, AsGetVersionInfoRequest, AsGetSelectedNodeEventRequest, \
    AsSceneLoadPlmXmlRequest, AsSceneCloseRequest
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class AsConnectorConnection:
    timeout = 60
    num_retries = 4

    def __init__(self):
        self._connected = False
        self.error = str()
        self.version = str()

    @property
    def connected(self):
        return self._connected

    @connected.setter
    def connected(self, value: bool):
        self._connected = value

    def check_connection(self) -> bool:
        version_request = AsGetVersionInfoRequest()
        result = self.request(version_request)
        selected_event = AsGetSelectedNodeEventRequest()
        selected_result = self.request(selected_event, False)

        if result or selected_result:
            self.version = version_request.result or str()
            LOGGER.debug(f'Connected to AsConnector {version_request.result or "<no version result!>"}')
            self.connected = True
        else:
            self.connected = False
            self.error = _('Konnte mit keiner AsConnector Instanz verbinden.')

        return result

    def request(self, as_request: AsConnectorRequest, retry: bool = True) -> bool:
        r, err, tries, result = None, str(), 0, False
        retries = self.num_retries if retry else 1

        while not result and (tries := tries + 1) <= retries:
            try:
                r = requests.post(
                    as_request.get_url(), data=as_request.to_bytes(), headers=as_request.get_header(),
                    timeout=self.timeout
                    )
            except Exception as e:
                LOGGER.error('Error connecting to AsConnector! %s', e)
                err = str(e)

            if r is not None:
                LOGGER.debug('Sent %s to AsConnector, response code was: %s', as_request.__class__.__name__,
                             r.status_code)
                result = as_request.handle_response(r)
                self.error = as_request.error
            else:
                self.error = str(err)
                result = False

        return result

    def initialize_as_connector(self, plmxml_file: Path) -> bool:
        """ Re-initialize AsConnector Id's and materials if e.g. DeltaGen scene changed
            1. AsSceneLoadPlmXmlRequest
            2. CloseScene
            -> AsConnector is now initialized to a new scene.
        """

        # -- Load PlmXml as DeltaGen Scene --
        load_request = AsSceneLoadPlmXmlRequest(plmxml_file)
        load_response = self.request(load_request, retry=False)

        if not load_response:
            return False

        # -- Close the loaded PlmXml --
        sleep(0.3)
        close_request = AsSceneCloseRequest(plmxml_file.name)
        close_result = self.request(close_request)

        if not close_result:
            return False
        sleep(0.2)

        return True
