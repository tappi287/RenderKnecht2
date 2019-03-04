from PySide2 import QtWidgets

from modules.settings import KnechtSettings
from modules.gui.gui_utils import ConnectCall
from modules.gui.widgets.message_box import GenericMsgBox
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
                  'Bitte File > Exit waehlen und Anwendung anschließend erneut starten.'
        else:
            title = 'Change Language'
            msg = 'The Application needs to be restarted to change the language to English.<br>' \
                  'Please choose Datei > Beenden to exit and then start the application again.'

        KnechtSettings.language = l

        msg_box = GenericMsgBox(self.ui, title, msg,
                                icon_key='reset')
        msg_box.exec()

    def update_menu(self):
        self.de.setChecked(False)
        self.en.setChecked(False)

        if KnechtSettings.language.casefold() == 'de':
            self.de.setChecked(True)
        elif KnechtSettings.language.casefold() == 'en':
            self.en.setChecked(True)
