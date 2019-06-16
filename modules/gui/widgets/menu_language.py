from PySide2 import QtWidgets

from modules.gui.ui_resource import IconRsc
from modules.knecht_update import restart_knecht_app
from modules.settings import KnechtSettings
from modules.gui.gui_utils import ConnectCall
from modules.gui.widgets.message_box import GenericMsgBox, AskToContinue
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class LanguageMenu(QtWidgets.QMenu):
    def __init__(self, ui: QtWidgets.QMainWindow):
        super(LanguageMenu, self).__init__(_("Sprache"), ui)
        self.ui = ui
        self.en, self.de = QtWidgets.QAction(), QtWidgets.QAction()
        self.setup()

    def setup(self):
        self.en = QtWidgets.QAction('English [en]', self)
        self.en.setCheckable(True)
        en_call = ConnectCall('en', target=self.change_language, parent=self.en)
        self.en.triggered.connect(en_call.call)

        self.de = QtWidgets.QAction('Deutsch [de]', self)
        self.de.setCheckable(True)
        de_call = ConnectCall('de', target=self.change_language, parent=self.de)
        self.de.triggered.connect(de_call.call)
        self.addActions([self.de, self.en])

        self.aboutToShow.connect(self.update_menu)

    def change_language(self, l: str):
        if KnechtSettings.language == l:
            return

        if 'de' == l:
            title = 'Sprache auswählen'
            msg = 'Die Anwendung muss neu gestartet werden um die Sprache auf Deutsch zu aendern.<br>' \
                  'Anwendung jetzt neustarten?'
            ok_btn = 'Neustarten'
            no_btn = 'Später neustarten..'
        else:
            title = 'Change Language'
            msg = 'The Application needs to be restarted to change the language to English.<br>' \
                  'Restart app now?'
            ok_btn = 'Restart'
            no_btn = 'Restar later..'

        KnechtSettings.language = l

        msg_box = AskToContinue(self.ui)
        if msg_box.ask(title, msg, ok_btn, no_btn):
            restart_knecht_app(self.ui)

    def update_menu(self):
        self.de.setChecked(False)
        self.en.setChecked(False)

        if KnechtSettings.language.casefold() == 'de':
            self.de.setChecked(True)
        elif KnechtSettings.language.casefold() == 'en':
            self.en.setChecked(True)
