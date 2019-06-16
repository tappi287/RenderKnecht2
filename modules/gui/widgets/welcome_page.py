from PySide2.QtCore import QEvent, Qt
from PySide2.QtWidgets import QPushButton, QVBoxLayout, QWidget, QGroupBox

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
    max_recent_entries = 5

    def __init__(self, ui):
        """ Generic welcome page

        :param modules.gui.main_ui.KnechtWindow ui: Knecht main window
        """
        super(KnechtWelcome, self).__init__()
        SetupWidget.from_ui_file(self, Resource.ui_paths['knecht_welcome'])
        self.ui = ui
        self.setWindowTitle(_('Willkommen'))

        self.title_label.setText(_('RenderKnecht v{}').format(KnechtSettings.app['version']))
        self.news_title.setText('Updates:')
        self.news_title.setStyleSheet('font-weight: 800;')
        self.create_box: QGroupBox
        self.create_box.setTitle(_('Erstellen'))
        self.recent_box.setTitle(_('Kürzlich verwendet'))

        self.new_btn.setText(_('Neues Dokument'))
        self.new_btn.released.connect(self.ui.main_menu.file_menu.new_document)

        self.open_btn.setText(_('Dokument öffnen'))
        self.open_btn.released.connect(self._open)

        self.import_btn: QPushButton
        self.import_btn.setText(_('Import'))
        self.import_btn.setMenu(self.ui.main_menu.file_menu.import_menu)

        self.recent_layout: QVBoxLayout = self.recent_layout
        self.recent_btns = list()

        # --- Update recent files ---
        self.ui.main_menu.file_menu.update_recent_files_menu()
        self.ui.main_menu.file_menu.recent_files_changed.connect(self.update_recent_entries)
        self.update_recent_entries()

    def _open(self):
        self.ui.main_menu.file_menu.open_xml()

    def _import(self):
        self.ui.main_menu.file_menu.import_menu.popup(self.import_btn.pos())

    def update_recent_entries(self):
        LOGGER.debug('Updating Welcome page recent entries.')
        self.setUpdatesEnabled(False)

        while self.recent_btns:
            btn = self.recent_btns.pop()
            self.recent_layout.removeWidget(btn)
            btn.deleteLater()

        spacer = self.recent_layout.takeAt(0)

        for action in self.ui.main_menu.file_menu.recent_menu.actions():
            btn = QPushButton(action.text(), self)
            btn.setIcon(action.icon())
            btn.released.connect(action.trigger)
            self.recent_btns.append(btn)
            self.recent_layout.addWidget(btn, alignment=Qt.AlignLeft)

            if len(self.recent_btns) > self.max_recent_entries:
                break

        self.recent_layout.addSpacerItem(spacer)

        self.setUpdatesEnabled(True)
