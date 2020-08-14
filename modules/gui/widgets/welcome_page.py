import time
from pathlib import Path

from PySide2.QtCore import Qt, QTimer, QFile, QIODevice, QByteArray
from PySide2.QtWidgets import QPushButton, QVBoxLayout, QWidget, QGroupBox

from modules import KnechtSettings
from modules.globals import Resource
from modules.gui.gui_utils import SetupWidget
from modules.itemview.xml import XmlWorkThread
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class KnechtWelcome(QWidget):
    max_recent_entries = 5
    skill_level = 0

    def __init__(self, ui):
        """ Generic welcome page

        :param modules.gui.main_ui.KnechtWindow ui: Knecht main window
        """
        super(KnechtWelcome, self).__init__()
        SetupWidget.from_ui_file(self, Resource.ui_paths['knecht_welcome'])
        self.ui = ui
        self.setWindowTitle(_('Start'))

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

        self.template_btn_plm: QPushButton
        self.template_btn_plm.setText(_('Knecht PlmXml Vorlage erzeugen'))
        self.template_btn_plm.released.connect(self.load_plmxml_template)

        self.template_btn_dap: QPushButton
        self.template_btn_dap.setText(_('Knecht Vorlage erzeugen'))
        self.template_btn_dap.released.connect(self.load_dap_template)

        self.step_up_box: QGroupBox
        self.step_up_box.setTitle('Step Up Your Game')

        self.wizard_shortcut: QPushButton
        self.wizard_shortcut.setText(_('Preset Wizard'))
        self.wizard_shortcut.pressed.connect(self.open_wizard)
        self.docs_shortcut: QPushButton
        self.docs_shortcut.setText(_('Dokumentation'))
        self.docs_shortcut.pressed.connect(self.open_docs)

        self.action_timer = QTimer()
        self.action_timer.setSingleShot(True)
        self.action_timer.setInterval(500)

        # --- Update recent files ---
        self.recent_layout: QVBoxLayout = self.recent_layout
        self.recent_btns = list()

        self.ui.main_menu.file_menu.update_recent_files_menu()
        self.ui.main_menu.file_menu.recent_files_changed.connect(self.update_recent_entries)
        self.update_recent_entries()

    def _action_timeout(self):
        if self.action_timer.isActive():
            return True
        self.action_timer.start()
        return False

    def _open(self):
        if self._action_timeout():
            return
        self.ui.main_menu.file_menu.open_xml()

    def _import(self):
        if self._action_timeout():
            return
        self.ui.main_menu.file_menu.import_menu.popup(self.import_btn.pos())

    def open_wizard(self):
        if self._action_timeout():
            return
        self._set_skill_level()
        self.ui.main_menu.file_menu.import_menu.open_wizard()

    def open_docs(self):
        if self._action_timeout():
            return
        self._set_skill_level()
        self.ui.main_menu.info_menu.show_docs()

    def _set_skill_level(self):
        self.skill_level += 1
        msg = 'Skill Level Increased '
        for x in range(0, self.skill_level):
            msg += '+'
        self.step_up_box.setTitle(msg[:50])

    def load_plmxml_template(self):
        self._load_template('knecht_plmxml_template', Path('Knecht_PlmXml_Template.xml'))

    def load_dap_template(self):
        self._load_template('knecht_dap_template', Path('Knecht_DAP_Template.xml'))

    def _load_template(self, file_key: str, display_file_path: Path):
        f = QFile(Resource.icon_paths.get(file_key))
        try:
            f.open(QIODevice.ReadOnly)
            data: QByteArray = f.readAll()
            self.ui.main_menu.file_menu.load_save_mgr.load_start_time = time.time()
            # noinspection PyTypeChecker
            xml_worker = XmlWorkThread(
                display_file_path,
                self.ui.main_menu.file_menu.load_save_mgr.xml_worker_queue,
                open_xml=False,  # We want to load from bytes
                xml_data=data.data()  # The Qt docs are wrong... returns bytes and not str
                )
            xml_worker.xml_items_loaded.connect(self.ui.main_menu.file_menu.load_save_mgr.load_thread_finished)
            xml_worker.start()
        except Exception as e:
            LOGGER.error(e)

    def update_recent_entries(self):
        LOGGER.debug('Updating Welcome page recent entries.')
        self.setUpdatesEnabled(False)

        while self.recent_btns:
            btn = self.recent_btns.pop()
            self.recent_layout.removeWidget(btn)
            btn.deleteLater()

        spacer = self.recent_layout.takeAt(0)

        for action in self.ui.main_menu.file_menu.recent_menu.actions():
            btn = QPushButton(self.shorten_action_text(action.text()), self)
            btn.setStatusTip(action.text())
            btn.setIcon(action.icon())
            btn.released.connect(action.trigger)
            self.recent_btns.append(btn)
            self.recent_layout.addWidget(btn, alignment=Qt.AlignLeft)

            if len(self.recent_btns) > self.max_recent_entries:
                break

        self.recent_layout.addSpacerItem(spacer)

        self.setUpdatesEnabled(True)

    @staticmethod
    def shorten_action_text(text):
        if len(text) < 50:
            return text

        return f'{text[:30]}~{text[-20:]}'
