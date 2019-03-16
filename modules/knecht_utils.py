import shutil
from pathlib import Path
from tempfile import mkdtemp
from zipfile import ZIP_LZMA, ZipFile

from modules.globals import get_settings_dir
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


def list_class_values(obj):
    if not hasattr(obj, '__dict__'):
        return []

    values = list()

    for k, v in obj.__dict__.items():
        if k.startswith('__'):
            continue
        values.append(v)

    return values


def list_class_fields(obj) -> dict:
    if not hasattr(obj, '__dict__'):
        return []

    attr = dict()

    for k, v in obj.__dict__.items():
        if k.startswith('__') or not isinstance(v, (int, str, float, bool, list, dict, tuple)):
            continue
        attr[k] = v

    return attr


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