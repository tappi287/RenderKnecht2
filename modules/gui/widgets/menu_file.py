from pathlib import Path

from PySide2.QtCore import QTimer, QObject, Slot
from PySide2.QtGui import QKeySequence
from PySide2.QtWidgets import QAction, QMenu

from modules.gui.widgets.menu_import import ImportMenu
from modules.gui.widgets.progress_overlay import ShowTreeViewProgressMessage
from modules.itemview.model import KnechtModel
from modules.settings import KnechtSettings
from modules.gui.ui_view_manager import UiViewManager
from modules.gui.ui_resource import IconRsc
from modules.itemview.xml import SaveLoadController
from modules.gui.widgets.file_dialog import FileDialog
from modules.language import get_translation
from modules.log import init_logging
from modules.gui.widgets.message_box import AskToContinue, XmlFailedMsgBox

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class FileMenu(QObject):
    new_document_count = 0
    current_progress_obj = ShowTreeViewProgressMessage(None)
    load_save_mgr = None

    def __init__(self, ui, menu: QMenu=None):
        """ The File menu

        :param modules.gui.main_ui.KnechtWindow ui:
        :param menu: Menu created setup in ui file
        """
        super(FileMenu, self).__init__(parent=ui)
        self.ui = ui
        self.view_mgr: UiViewManager = None

        self.menu = menu or ui.menuDatei
        self.menu.setEnabled(False)
        self.recent_menu = QMenu(_('Zuletzt geöffnet'), self.menu)
        self.import_menu = ImportMenu(self.ui)
        self.import_menu.new_model_ready.connect(self.model_loaded)

        self.xml_message_box = XmlFailedMsgBox(self.ui)

        self.setup_file_menu()
        QTimer.singleShot(1, self.delayed_setup)

    @Slot()
    def delayed_setup(self):
        """ Setup attributes that require a fully initialized ui"""
        self.view_mgr: UiViewManager = self.ui.view_mgr
        self.menu.setEnabled(True)

        self.load_save_mgr = SaveLoadController(self)
        self.load_save_mgr.model_loaded.connect(self.model_loaded)
        self.load_save_mgr.load_aborted.connect(self._load_aborted)

    def setup_file_menu(self):
        insert_before = 0
        if self.ui.actionBeenden in self.menu.actions():
            insert_before = self.ui.actionBeenden
            self.ui.actionBeenden.setIcon(IconRsc.get_icon('sad'))
            self.ui.actionBeenden.setShortcut(QKeySequence('Ctrl+Q'))

        # ---- New file ----
        new_action = QAction(IconRsc.get_icon('document'), _('Neu\tStrg+N'), self.menu)
        new_action.setShortcut(QKeySequence('Ctrl+N'))
        new_action.triggered.connect(self.new_document)
        self.menu.insertAction(insert_before, new_action)

        # ---- Open ----
        open_xml_action = QAction(_('Öffnen\tStrg+O'), self.menu)
        open_xml_action.setShortcut(QKeySequence('Ctrl+O'))
        open_xml_action.triggered.connect(self.open_xml)
        open_xml_action.setIcon(IconRsc.get_icon('folder'))
        self.menu.insertAction(insert_before, open_xml_action)

        # ---- Import Menu ----
        self.menu.insertMenu(insert_before, self.import_menu)

        # ---- Save ----
        save_xml_action = QAction(_('Speichern\tStrg+S'), self.menu)
        save_xml_action.setShortcut(QKeySequence('Ctrl+S'))
        save_xml_action.triggered.connect(self.save_xml)
        save_xml_action.setIcon(IconRsc.get_icon('disk'))
        self.menu.insertAction(insert_before, save_xml_action)

        save_as_action = QAction(_('Speichern unter ...\tStrg+Shift+S'), self.menu)
        save_as_action.setShortcut(QKeySequence('Ctrl+Shift+S'))
        save_as_action.triggered.connect(self.save_as_xml)
        save_as_action.setIcon(IconRsc.get_icon('save_alt'))
        self.menu.insertAction(insert_before, save_as_action)

        self.menu.insertSeparator(insert_before)

        # ---- Recent files menu ----
        self.recent_menu.aboutToShow.connect(self.update_recent_files_menu)
        self.menu.insertMenu(insert_before, self.recent_menu)

        self.menu.insertSeparator(insert_before)

    def new_document(self):
        new_file = Path(_('Neues_Dokument_{:02d}.xml').format(self.new_document_count))
        self.view_mgr.create_view(None, new_file)

        self.new_document_count += 1

    def save_xml(self):
        self.enable_menus(False)

        file = self.view_mgr.current_file()

        if not file or not file.exists():
            if self._ask_save_as_file(file):
                # User agreed to set new save file
                self.save_as_xml()
                return
            # User aborted
            self.enable_menus(True)
            return

        self.save_as_xml(file)

    def save_as_xml(self, file: Path=None):
        self.enable_menus(False)

        if not file:
            current_dir = Path(KnechtSettings.app['current_path'])
            file, file_type = FileDialog.save(self.ui, current_dir, file_key='xml')

        if not file:
            LOGGER.info('Save Xml File dialog canceled.')
            self.enable_menus(True)
            return

        file = Path(file)
        view = self.view_mgr.current_view()

        result, error = self.load_save_mgr.save(file, view)

        if result:
            LOGGER.debug('File saved: %s', file.as_posix())
            self.view_mgr.tab_view_saved(file)
            self.ui.msg(_('Datei gespeichert:{0}{1:.3}s').format(f'\n{file.name}\n',
                                                                    self.load_save_mgr.last_progress_time))
        else:
            self._save_aborted(error, file)

        self.enable_menus(True)

    def open_xml(self, file: str=None) -> None:
        self.enable_menus(False)

        if not file:
            file = FileDialog.open(self.ui, None, 'xml')

        if not file:
            LOGGER.info('Open Xml File dialog canceled.')
            self.enable_menus(True)
            return

        # Check if the file is already opened
        file = Path(file)
        if self.view_mgr.file_mgr.already_open(file):
            LOGGER.info('File already open.')
            self.enable_menus(True)
            return

        # Update treeview progress
        view = self.view_mgr.current_view()
        view.progress_msg.msg(_('Daten werden gelesen'))
        view.progress_msg.show_progress()

        self.load_save_mgr.open(file)
        self.enable_menus(True)

    @Slot(KnechtModel, Path)
    def model_loaded(self, model: KnechtModel, file: Path):
        # Update progress
        view = self.view_mgr.current_view()
        view.progress_msg.hide_progress()

        # Create a new view inside a new tab or load into current view if view model is empty
        new_view = self.view_mgr.create_view(model, file)

        # Refresh model data
        new_view.model().sourceModel().initial_item_id_connection()
        new_view.model().sourceModel().refreshData()

        self.ui.statusBar().showMessage(_('{0} in {1:.3}s geladen.'
                                          ).format(file.name, self.load_save_mgr.last_progress_time))

    @Slot(str, Path)
    def _load_aborted(self, error_msg: str, file: Path):
        # Update progress
        view = self.view_mgr.current_view()
        view.progress_msg.hide_progress()

        self.xml_message_box.set_error_msg(error_msg, Path(file))

        self.ui.play_warning_sound()
        self.xml_message_box.exec_()

    def _save_aborted(self, error_msg: str, file: Path):
        self.xml_message_box.set_error_msg(error_msg, Path(file))

        self.ui.play_warning_sound()
        self.xml_message_box.exec_()

    def enable_menus(self, enabled: bool=True):
        for a in self.menu.actions():
            a.setEnabled(enabled)

        self.recent_menu.setEnabled(enabled)

    def _open_recent_xml_file(self):
        recent_action = self.sender()
        self.open_xml(recent_action.file)

    def _open_recent_xlsx_file(self):
        recent_action = self.sender()
        self.import_menu.open_xlsx(recent_action.file)

    def _ask_save_as_file(self, file: Path):
        """ User hits save but file to save does not exist yet """
        msg_box = AskToContinue(self.ui)

        if not msg_box.ask(_('Zieldatei zum Speichern festlegen?'),
                           _('Die Datei: <i>{}</i><br>'
                             'Pfad: <i>{}</i><br>'
                             'wurde entfernt oder existiert nicht mehr.<br><br>'
                             'Neue Zieldatei zum Speichern festlegen?'
                             '').format(file.name, file.parent.as_posix()),
                           _('Speichern unter..')):
            # User wants to abort save as
            return False
        return True

    def update_recent_files_menu(self):
        self.recent_menu.clear()

        if not len(KnechtSettings.app['recent_files']):
            no_entries_dummy = QAction(_("Keine Einträge vorhanden"), self.recent_menu)
            no_entries_dummy.setEnabled(False)
            self.recent_menu.addAction(no_entries_dummy)

        for idx, entry in enumerate(KnechtSettings.app['recent_files']):
            if idx >= 20:
                break

            file, file_type = entry
            file_name = Path(file).name

            if not Path(file).exists():
                # Skip and remove non existing files
                KnechtSettings.app['recent_files'].pop(idx)
                continue

            recent_action = QAction(f'{file_name} - {file_type}', self.recent_menu)
            recent_action.file = Path(file)

            if file_type == 'xml':
                recent_action.setIcon(IconRsc.get_icon('document'))
                recent_action.triggered.connect(self._open_recent_xml_file)
            elif file_type == 'xlsx':
                recent_action.setIcon(IconRsc.get_icon('excel'))
                recent_action.triggered.connect(self._open_recent_xlsx_file)

            self.recent_menu.addAction(recent_action)
