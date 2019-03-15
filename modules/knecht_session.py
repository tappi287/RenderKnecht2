from pathlib import Path
from typing import List, Tuple
from zipfile import ZipFile

from PySide2.QtCore import Slot, QObject, QTimer, Qt, QEvent
from PySide2.QtWidgets import QWidget

from modules.itemview.model import KnechtModel
from modules.itemview.model_update import UpdateModel
from modules.itemview.xml import SaveLoadController
from modules.knecht_utils import CreateZip
from modules.settings import Settings
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class KnechtSession(QObject):
    session_zip = CreateZip.settings_dir / 'Session_data.zip'
    files_list_name = 'session_files.json'

    class FileNameStorage:
        def __init__(self):
            self.store = dict()

    def __init__(self, ui, idle_save: bool=False):
        """ Save and restore user session of opened documents

        :param modules.gui.main_ui.KnechtWindow ui: The main UI window
        :param bool idle_save: auto save session when UI is idle
        """
        super(KnechtSession, self).__init__(ui)
        self.restore_files_storage = self.FileNameStorage()

        self.load_save_mgr = SaveLoadController(self)
        # Load models into views and associate original save file path
        self.load_save_mgr.model_loaded.connect(self.model_loaded)
        # We will silently ignore load errors on session restore
        self.load_save_mgr.load_aborted.connect(self._load_next)

        self.idle_timer = QTimer()
        self.save_timer = QTimer()
        self.idle = False

        if idle_save:
            self.idle_timer.setSingleShot(True)
            self.save_timer.setSingleShot(True)
            self.idle_timer.setTimerType(Qt.VeryCoarseTimer)
            self.save_timer.setTimerType(Qt.VeryCoarseTimer)
            self.idle_timer.setInterval(10000)
            self.save_timer.setInterval(10000)

            # Detect inactivity for automatic session save
            self.idle_timer.timeout.connect(self.set_inactive)
            self.save_timer.timeout.connect(self.auto_save)
            ui.app.installEventFilter(self)

        self.ui = ui
        self.load_dir = None
        self.load_queue = list()

    def set_active(self):
        self.idle = False
        self.idle_timer.start()

    def set_inactive(self):
        self.idle = True
        self.save_timer.start()
        LOGGER.debug('Idling.')

    def eventFilter(self, obj, eve):
        if eve is None or obj is None:
            return False

        if eve.type() == QEvent.KeyPress or \
           eve.type() == QEvent.MouseMove or \
           eve.type() == QEvent.MouseButtonPress:
            self.set_active()
            return False

        return False

    def _load_next(self):
        if not self.load_queue:
            self.restore_finished()
            return

        file = self.load_queue.pop()
        file = self.load_dir / file.name
        self.load_save_mgr.open(file)

    @Slot(KnechtModel, Path)
    def model_loaded(self, model: KnechtModel, file: Path):
        LOGGER.debug('Restoring: %s', file.name)
        # Update progress
        view = self.ui.view_mgr.current_view()
        view.progress_msg.hide_progress()

        # Restore original save path
        if file.name in self.restore_files_storage.store:
            file = Path(self.restore_files_storage.store[file.name])

        if file.name == 'Variants_Tree.xml':
            # Update Variants Tree
            update_model = UpdateModel(self.ui.variantTree)
            update_model.update(model)
            new_view = self.ui.variantTree
        else:
            # Create a new view inside a new tab or load into current view if view model is empty
            new_view = self.ui.view_mgr.create_view(model, file)

        # Refresh model data
        new_view.model().sourceModel().initial_item_id_connection()
        new_view.model().sourceModel().refreshData()

        self._load_next()

    def auto_save(self):
        if self.load_queue or not self.idle:
            return

        self.save()

    def save(self) -> bool:
        tmp_dir = CreateZip.create_tmp_dir()
        file_names = self.FileNameStorage()
        result = True
        count = 0

        documents_list = list()
        documents_list.append(
            (self.ui.variantTree, Path('Variants_Tree.xml'))
            )

        for widget, file in zip(self.ui.view_mgr.file_mgr.widgets, self.ui.view_mgr.file_mgr.files):
            if hasattr(widget, 'user_view'):
                documents_list.append(
                    (widget.user_view, file)
                    )

        for view, file in documents_list:
            if not view.model().rowCount() or not file:
                continue

            # Rename duplicate file names
            if file.name in file_names.store:
                count += 1
                file = file.parent / Path(file.stem + f'{count:02d}' + file.suffix)

            # Save document
            tmp_file = tmp_dir / file.name
            r, _ = self.load_save_mgr.save(tmp_file, view)

            if not r:
                result = False
            else:
                file_names.store[file.name] = file.as_posix()
                LOGGER.debug('Saved session document: %s', tmp_file.name)

        # Save original file paths stored in Files class
        Settings.save(file_names, tmp_dir / self.files_list_name)

        if not CreateZip.save_dir_to_zip(tmp_dir, self.session_zip):
            result = False

        CreateZip.remove_dir(tmp_dir)
        return result

    def restore(self) -> bool:
        """ Restore a user session asynchronous """
        if not self.session_zip.exists():
            return False

        self.load_dir = CreateZip.create_tmp_dir()

        try:
            with ZipFile(self.session_zip, 'r') as zip_file:
                zip_file.extractall(self.load_dir)
        except Exception as e:
            LOGGER.error(e)
            return False

        # Restore original file save paths
        Settings.load(self.restore_files_storage, self.load_dir / self.files_list_name)

        for file in self.load_dir.glob('*.xml'):
            LOGGER.debug('Starting restore of document: %s @ %s',
                         file.name, self.restore_files_storage.store.get(file.name))
            self.load_queue.append(file)

        self._load_next()
        return True

    def restore_finished(self):
        CreateZip.remove_dir(self.load_dir)
        LOGGER.debug('Session restored.')
