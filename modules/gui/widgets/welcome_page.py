from PySide2.QtCore import Qt
from PySide2.QtWidgets import QLabel, QVBoxLayout, QWidget, QPushButton

from modules import KnechtSettings
from modules.globals import Resource
from modules.gui.gui_utils import SetupWidget
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class KnechtWelcome(QWidget):
    def __init__(self, ui):
        """ Generic welcome page

        :param modules.gui.main_ui.KnechtWindow ui: Knecht main window
        """
        super(KnechtWelcome, self).__init__(ui)
        SetupWidget.from_ui_file(self, Resource.ui_paths['knecht_welcome'])
        self.ui = ui
        self.setWindowTitle(_('Willkommen'))

        self.title_label.setText(_('RenderKnecht v{}').format(KnechtSettings.app['version']))

        self.recent_layout: QVBoxLayout = self.recent_layout
        self.recent_btns = list()

        self.update()

    def update(self):
        self.setUpdatesEnabled(False)
        self.ui.main_menu.file_menu.update_recent_files_menu()

        while self.recent_btns:
            btn = self.recent_btns.pop()
            self.recent_layout.removeWidget(btn)
            btn.deleteLater()

        for action in self.ui.main_menu.file_menu.recent_menu.actions():
            btn = QPushButton(action.text(), self)
            btn.setIcon(action.icon())
            btn.setStyleSheet('background: transparent;')
            btn.released.connect(action.trigger)
            self.recent_btns.append(btn)
            self.recent_layout.addWidget(btn, alignment=Qt.AlignLeft)

        self.setUpdatesEnabled(True)
