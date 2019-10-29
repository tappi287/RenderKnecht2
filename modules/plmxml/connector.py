import requests

from modules.plmxml import LOGGER
from modules.plmxml.request import AsConnectorRequest
from modules.language import get_translation


# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class AsConnectorConnection:
    def __init__(self):
        self.error = str()

    def request(self, as_request: AsConnectorRequest) -> bool:
        r = requests.post(
            as_request.get_url(), data=as_request.to_bytes(), headers=as_request.get_header()
            )

        LOGGER.debug('Sent request to AsConnector, response code was: %s', r.status_code)

        if r.ok:
            LOGGER.debug(r.text)
            return True
        else:
            LOGGER.error('Error while sending request:\n%s', as_request.to_string())
            LOGGER.error('AsConnector result:\n%s', r.text)
            self.error = f'Error while sending {type(as_request)} request.' \
                         f'\nAsConnector returned:\n{r.text}'

        return False
