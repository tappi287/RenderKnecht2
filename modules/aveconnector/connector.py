import requests

from modules.aveconnector.request import AVERequest
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class AVEConnection:
    timeout = 60
    num_retries = 4

    def __init__(self):
        self.error = str()

    def request(self, ave_request: AVERequest, retry: bool = True) -> bool:
        r, err, tries, result = None, str(), 0, False
        retries = self.num_retries if retry else 1

        while not result and (tries := tries + 1) <= retries:
            try:
                r = requests.post(
                    ave_request.get_url(), json=ave_request.get_json(), timeout=self.timeout
                    )
            except Exception as e:
                LOGGER.error('Error connecting to AVE! %s', e)
                err = str(e)

            if r is not None:
                LOGGER.debug('Sent %s to AVE, response code was: %s', ave_request.__class__.__name__,
                             r.status_code)
                result = ave_request.handle_response(r)
                self.error = ave_request.error
            else:
                self.error = str(err)
                result = False

        return result
