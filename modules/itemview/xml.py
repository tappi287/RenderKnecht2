import time
from pathlib import Path
from queue import Queue
from threading import Thread
from typing import Union

from PySide2.QtCore import QObject, Signal, Slot

from modules.gui.widgets.path_util import path_exists
from modules.itemview.item import KnechtItem
from modules.itemview.model import KnechtModel
from modules.itemview.tree_view import KnechtTreeView
from modules.itemview.xml_read import KnechtOpenXml
from modules.itemview.xml_save import KnechtSaveXml
from modules.language import get_translation
from modules.log import init_logging
from modules.settings import KnechtSettings

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class XmlWorkThreadSignals(QObject):
    xml_items_loaded = Signal()


class XmlWorkThread(Thread):
    def __init__(self, file: Union[Path, str], queue: Queue, xml_data: bytes=b'', open_xml: bool=True):
        super(XmlWorkThread, self).__init__()
        self.load_mode = open_xml
        self.file = file
        self.xml_data = xml_data
        self.queue = queue

        self.signals = XmlWorkThreadSignals()
        self.xml_items_loaded = self.signals.xml_items_loaded

    def run(self):
        if self.load_mode:
            self.load_xml()
        else:
            self.load_from_bytes()

    def load_xml(self):
        root_item, error_str = KnechtOpenXml.read_xml(self.file)
        self.xml_items_loaded.emit()
        self.queue.put(
            (root_item, error_str, self.file)
            )

    def load_from_bytes(self):
        root_item, error_str = KnechtOpenXml.read_xml(self.xml_data)
        self.xml_items_loaded.emit()
        self.queue.put(
            (root_item, error_str, self.file)
            )


class SaveLoadController(QObject):
    model_loaded = Signal(KnechtModel, Path)
    load_aborted = Signal(str, Path)

    load_start_time = float()
    last_progress_time = float()

    def __init__(self, parent: Union[None, QObject], create_recent_entries: bool=True):
        super(SaveLoadController, self).__init__(parent)

        self.xml_worker = None
        self.xml_worker_queue = Queue()

        self.create_recent_entries = create_recent_entries

    def save(self, file: Union[Path, str], view: KnechtTreeView):
        src_model = view.model().sourceModel()
        file = Path(file)
        start_time = time.time()
        result, error = KnechtSaveXml.save_xml(file, src_model)

        if result:
            if self.create_recent_entries:
                KnechtSettings.add_recent_file(file.as_posix(), 'xml')
                KnechtSettings.app['current_path'] = file.parent.as_posix()
            self.last_progress_time = time.time() - start_time

        return result, error

    def open(self, file: Union[Path, str]):
        file = Path(file)

        if not path_exists(file):
            LOGGER.info('The provided Xml path does not seem to exist or is un-accessible.')
            self.load_aborted.emit(_('Kann nicht auf die gewählte Datei zugreifen.'), file)
            return

        self.load_start_time = time.time()

        self.xml_worker = XmlWorkThread(file, self.xml_worker_queue, open_xml=True)
        self.xml_worker.xml_items_loaded.connect(self.load_thread_finished)

        self.xml_worker.start()

    @Slot()
    def load_thread_finished(self):
        try:
            root_item, error_str, file = self.xml_worker_queue.get(timeout=2)

            _root_item = self.copy_item_to_main_thread(root_item)
            root_item.deleteLater()
            self._xml_items_loaded(_root_item, error_str, file)
        except TimeoutError:
            self.load_aborted.emit(_('Allgemeiner Fehler beim laden der Daten.'), Path('.'))

    @Slot(KnechtItem, str, Path)
    def _xml_items_loaded(self, root_item: KnechtItem, error: str, file: Path):
        if not root_item.childCount():
            LOGGER.info('Could not load Xml. KnechtXml returned %s', error)
            self.load_aborted.emit(error, file)
            return

        # Transfer root_item to new_model
        new_model = KnechtModel(root_item)

        # Add recent file entry
        if self.create_recent_entries:
            KnechtSettings.add_recent_file(file.as_posix(), 'xml')
            KnechtSettings.app['current_path'] = file.parent.as_posix()

        # Output load info
        self.last_progress_time = time.time() - self.load_start_time

        LOGGER.info(f'Xml file {file.name} took {self.last_progress_time:.4}s to parse. {root_item.thread()}')

        # Transfer model
        self.model_loaded.emit(new_model, file)

    @staticmethod
    def copy_item_to_main_thread(root_item: KnechtItem):
        """ Creates a copy of a loaded root item that lives in the main thread """

        # Create root item that lives in the main thread
        _root_item = KnechtItem()

        # Copy child items from loaded item to the main thread root item
        root_item.copy_children(_root_item)

        return _root_item
