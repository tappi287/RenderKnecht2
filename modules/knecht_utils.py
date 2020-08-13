import re
import time
import shutil
from pathlib import Path
from socket import AF_INET, SOCK_DGRAM, socket, timeout
from tempfile import mkdtemp
from threading import Thread
from zipfile import ZIP_LZMA, ZipFile

from PySide2.QtCore import Signal, QObject

from modules.globals import get_settings_dir, SocketAddress
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class CreateZip:
    settings_dir = Path(get_settings_dir())

    @staticmethod
    def create_tmp_dir() -> Path:
        tmp_dir = Path(mkdtemp())
        return tmp_dir

    @staticmethod
    def save_dir_to_zip(dir_path: Path, zip_file: Path) -> bool:
        with ZipFile(zip_file, 'w') as zip_obj:
            for f in Path(dir_path).glob('*'):
                try:
                    zip_obj.write(f, arcname=f.name, compress_type=ZIP_LZMA)
                except Exception as e:
                    LOGGER.error(e)
                    return False

        return True

    @staticmethod
    def remove_dir(dir_path: Path):
        try:
            shutil.rmtree(dir_path)
        except Exception as e:
            LOGGER.error(e)


def search_list_indices(ls: list, value):
    idx: int = 0

    for i in range(0, ls.count(value)):
        # Search smallest known index + 0 or 1
        search_idx = idx + min(1, i)

        if value not in ls[search_idx:]:
            break

        idx = ls.index(value, search_idx)
        yield idx


def list_class_values(obj) -> dict:
    if not hasattr(obj, '__dict__'):
        return dict()

    class_dict = dict()

    for k in dir(obj):
        v = getattr(obj, k)
        if k.startswith('__') or not isinstance(v, (int, str, float, bool, list, dict, tuple)):
            continue
        class_dict[k] = v

    return class_dict


def time_string(time_f: float) -> str:
    """ Converts time in float seconds to display format

        Returned formats based on detected size (hours > minutes > seconds > milliseconds)

        * 01h:01min:01sec
        * 01min:01sec
        * 01sec
        * 001msec
    """
    m, s = divmod(time_f, 60)
    h, m = divmod(m, 60)

    if h < 1:
        if m < 1 and s < 1:
            msec = int(s * 1000)
            return '{:=03d}msec'.format(msec)

        if m < 1:
            return '{:=02.0f}sec'.format(s)

        return '{:=02.0f}min:{:=02.0f}sec'.format(m, s)
    else:
        return '{:=01.0f}h:{:=02.0f}min:{:=02.0f}sec'.format(h, m, s)


def shorten_model_name(model_name, num_words: int = 6, shorten: bool = False):
    # Remove horse power description
    model_name = re.sub(r'(\d?\d\d)[()](...........)\s', '', model_name)
    # Replace to one word
    model_name = re.sub(r'(S\sline)', 'S-line', model_name)
    model_name = re.sub(r'(S\stronic)', 'S-tronic', model_name)
    model_name = re.sub(r'(RS\s)', 'RS', model_name)

    # Split and make sure end index is not smaller than number of words
    # (Do not limit num of words if no shorten set)
    model_name = model_name.split(' ')
    if len(model_name) < num_words or not shorten:
        num_words = len(model_name)

    # If shorten is set, limit to 5 chars/word
    short_name = ''
    for m in model_name[0:num_words]:
        if shorten:
            short_name += m[0:5] + ' '
        else:
            short_name += m + ' '

    # Readability
    short_name = re.sub(r'(quatt\s)', 'quattro ', short_name, flags=re.I)
    short_name = re.sub(r'(Limou\s)', 'Limo ', short_name)
    short_name = re.sub(r'(allro\s)', 'allroad ', short_name)
    short_name = re.sub(r'(desig\s)', 'design ', short_name)
    short_name = re.sub(r'(RSD)', 'RS D', short_name)
    short_name = re.sub(r'(Navig\s)', 'Navi ', short_name, flags=re.I)
    short_name = re.sub(r'(Premi\s)', 'Prem ', short_name, flags=re.I)
    short_name = re.sub(r'(packa\s)', 'Pkg ', short_name, flags=re.I)
    short_name = re.sub(r'(Techn\s)', 'Tech ', short_name, flags=re.I)
    short_name = re.sub(r'(Advan\s)', 'Adv ', short_name, flags=re.I)

    return short_name


def get_service_address():
    search_timeout = 20  # Search for x seconds
    socket_timeout = 2
    service_address, data = None, None

    s = socket(AF_INET, SOCK_DGRAM)  # create UDP socket
    s.settimeout(socket_timeout)
    s.bind(('', SocketAddress.service_port))
    LOGGER.debug('Listening to service announcement on %s', SocketAddress.service_port)

    s_time = time.time()

    while 1:
        try:
            data, addr = s.recvfrom(1024)  # wait for a packet
            data = data.decode(encoding='utf-8')
            LOGGER.debug('Service listener received: %s', data)
        except timeout:
            pass

        if data:
            if data.startswith(SocketAddress.service_magic):
                service_address = data[len(SocketAddress.service_magic):]
                LOGGER.debug('Received service announcement from %s', service_address)

        if (time.time() - s_time) > search_timeout or service_address:
            break

    s.close()
    return service_address


class GetPfadAeffchenServiceSignals(QObject):
    result = Signal(object)


class GetPfadAeffchenService(Thread):
    signals = GetPfadAeffchenServiceSignals()
    result = signals.result
    service_address = None

    def __init__(self):
        super(GetPfadAeffchenService, self).__init__()

    def run(self):
        self.service_address = get_service_address()

        if self.service_address:
            self.result.emit(self.service_address)
        else:
            self.result.emit(False)


def create_file_safe_name(filename: str) -> str:
    """ Replace any non alphanumeric characters from a string expect minus/underscore/period """
    return re.sub('[^\\w\\-_\\.]', '_', filename)
