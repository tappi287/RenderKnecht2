import os
import locale
import ctypes
from gettext import translation

from modules.globals import get_current_modules_dir


def get_ms_windows_language():
    """ Currently we only support english and german """
    windll = ctypes.windll.kernel32

    # Get the language setting of the Windows GUI
    try:
        os_lang = windll.GetUserDefaultUILanguage()
    except Exception as e:
        print(e)
        return

    # Convert language code to string
    lang = locale.windows_locale.get(os_lang)

    # Only return supported languages
    if not lang.startswith('de'):
        lang = 'en'

    # Return de or en
    return lang[:2]


def setup_translation(language=None):
    if not language:
        if not os.environ.get('LANGUAGE'):
            # Set from OS language en or de
            os.environ.setdefault('LANGUAGE', get_ms_windows_language())
    else:
        # Set language from settings
        os.environ.setdefault('LANGUAGE', language)


def get_translation():
    # Set OS language if not already set
    lang = os.environ.get('LANGUAGE')

    if not lang:
        print('Setting language from OS.')
        os.environ.setdefault('LANGUAGE', get_ms_windows_language())
        print('Local Language detected: ' + os.environ.get('LANGUAGE'))

    locale_dir = os.path.join(get_current_modules_dir(), 'locale')
    return translation('knecht', localedir=locale_dir, codeset='UTF-8')
