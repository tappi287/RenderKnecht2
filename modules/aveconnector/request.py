from typing import List, Optional, Union

from requests import Response

from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class AVERequest:
    """ Request to AVE UE backend """
    ave_port = 4242
    ave_host_port = 4343
    base_url = f'http://localhost:{ave_port}/'
    base_header = {'Content-Type': 'application/json', 'Accept': 'text/plain'}

    def __init__(self, url: Optional[str] = None):
        self._data: Optional[Union[str, list, dict]] = None

        if url is None:
            LOGGER.warning('AVEConnectorRequest subclass: %s did not define request URL!', self.__class__.__name__)

        self.url: str = url or ''
        self.error = _('Kein Fehler definiert.')

    @property
    def data(self) -> Optional[Union[str, list, dict]]:
        return self._data

    @data.setter
    def data(self, value: Union[str, list, dict]):
        self._data = value

    def get_json(self) -> Optional[Union[str, list, dict]]:
        return self.data

    def get_url(self) -> str:
        return f'{self.base_url}{self.url}'

    def get_header(self) -> dict:
        header = dict()
        header.update(self.base_header)
        return header

    def handle_response(self, r: Response) -> bool:
        """ Handle the AVE http response """
        if self._read_response(r):
            return True

        LOGGER.error('Error while sending request to %s:\n%s', self.get_url(), self.get_json())
        LOGGER.error('AVEConnector Request result:\n%s', r.text)
        return self._read_error_response(r)

    def _read_response(self, r: Response) -> bool:
        """ Read the response Xml in individual requests sub classes """
        if r.ok:
            LOGGER.debug('AVEConnector response to %s was OK.', self.__class__.__name__)
            return True
        return False

    def _read_error_response(self, r: Response) -> bool:
        self.error = _('Fehler beim senden von {} Anfrage.').format(self.__class__.__name__)
        self.error += '\n'
        self.error += _('AVE antwortete:')
        self.error += f'\n{r.text[:500]}'
        return False


class AVEConfigurationRequest(AVERequest):
    def __init__(self, config: List[str]):
        super(AVEConfigurationRequest, self).__init__('events')
        self.config = config
        self._setup_request()

    def _setup_request(self):
        """ Setup JSON request expected by local AVE backend """
        data = dict()
        data['meta'] = {'name': 'AVEChangeCar', 'type': 'REQUEST', 'lastUpdate': True}
        data['data'] = {'carId': 'current', 'aveCarConfiguration': {'prCode': self.config}}

        # AVE expects JSON data wrapped in a list
        self.data = [data]
