from pathlib import Path

from PySide2.QtCore import QItemSelectionModel, QMimeData, QModelIndex, QObject, Qt, QTimer
from PySide2.QtGui import QDragMoveEvent, QDropEvent

from modules.gui.clipboard import TreeClipboard
from modules.gui.widgets.path_util import path_exists
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.knecht_camera import KnechtImageCameraInfo
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class KnechtDragDrop(QObject):
    clear_select_current_flags = (QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
    supported_file_types = ('.png', '.exr')

    def __init__(self, view):
        """ KnechtTreeView Helper class to handle item drag and drop

        :param modules.gui.main_ui.KnechtWindow ui:
        :param modules.itemview.tree_view.KnechtTreeView view:
        """
        super(KnechtDragDrop, self).__init__(view)
        self.view = view

        # Create a drag n drop specific clipboard
        self.clipboard = TreeClipboard()

        self.camera_item_verification_timer = QTimer()
        self.camera_item_verification_timer.setSingleShot(True)
        self.camera_item_verification_timer.timeout.connect(self._verify_camera_items_deferred)

        # Overwrite tree drop event
        view.dropEvent = self.drop_event
        view.dragMoveEvent = self.drag_move_event

    def drag_move_event(self, e: QDragMoveEvent):
        src = e.source()

        if e.mimeData().hasUrls():
            e.setDropAction(Qt.LinkAction)
            e.accept(self.view.rect())

        if isinstance(src, self.view.__class__):
            e.setDropAction(Qt.MoveAction)

            if src is not self.view:
                e.setDropAction(Qt.CopyAction)

            if e.keyboardModifiers() == Qt.ShiftModifier:
                e.setDropAction(Qt.CopyAction)

            e.accept(self.view.rect())

    def drop_event(self, e: QDropEvent):
        mime: QMimeData = e.mimeData()
        src = e.source()

        # -- File drop --
        if mime.hasUrls():
            destination_index = self.view.indexAt(e.pos())
            for url in mime.urls():
                local_path = Path(url.toLocalFile())
                if not path_exists(local_path):
                    continue

                self.file_drop(local_path, destination_index)

            e.accept()
            return

        # --- Internal View Drops ---
        if not isinstance(src, self.view.__class__):
            e.ignore()
            return

        e.setDropAction(Qt.MoveAction)

        if src is not self.view:
            e.setDropAction(Qt.CopyAction)

        if e.keyboardModifiers() == Qt.ShiftModifier:
            e.setDropAction(Qt.CopyAction)

        # -- Copy drop --
        if e.dropAction() is Qt.CopyAction:
            destination_index = self.view.indexAt(e.pos())
            self.copy_drop(src, destination_index)
            e.accept()

        # -- Drag move --
        if e.dropAction() is Qt.MoveAction:
            destination_index = self.view.indexAt(e.pos())
            self.move_drop(destination_index)

            # Ignore default view behaviour
            e.ignore()

    def move_drop(self, destination_index: QModelIndex):
        if not self.view.supports_drag_move:
            return
        LOGGER.debug('Drop with MoveAction at Proxy @%sP%s', destination_index.row(), destination_index.parent().row())
        self.view.editor.move_rows(destination_index)

    def copy_drop(self, source_view, destination_index):
        if not self.view.supports_drop:
            return

        LOGGER.debug('Drop with CopyAction at @%sP%s', destination_index.row(), destination_index.parent().row())

        result = self._copy(source_view)

        if not result:
            return

        self._select_drop_index(destination_index)

        self._paste()

    def file_drop(self, file: Path, destination_index: QModelIndex):
        self._select_drop_index(destination_index)
        order = int(destination_index.siblingAtColumn(Kg.ORDER).data(Qt.DisplayRole) or '-1') + 1
        LOGGER.debug('File Drop@%s: %s', order, file.as_posix())

        if file.suffix.casefold() in self.supported_file_types:
            cam_info_img = KnechtImageCameraInfo(file)
            cam_info_img.read_image()

            if cam_info_img.is_valid():
                cam_item = self.view.editor.create.create_camera_item(file.name, cam_info_img.camera_info)
                cam_item.setData(Kg.ORDER, f'{order:03d}')
                self.view.editor.create_top_level_rows([cam_item])
            else:
                if cam_info_img.file_is_valid and not cam_info_img.info_is_valid:
                    self.view.info_overlay.display(_('Keine Kamera Daten in Datei gefunden.\n'), 3000)
                    LOGGER.error('Camera data could not be found in %s', file.as_posix())
                else:
                    self.view.info_overlay.display(_('Konnte Datei mit Kamera Daten nicht lesen.\n'), 3000)
                    LOGGER.error('Could not read file with camera data %s', file.as_posix())
        else:
            self.view.file_dropped.emit(file)
            return

        # Validate created camera items
        self.camera_item_verification_timer.start(150)

    def _verify_camera_items_deferred(self):
        KnechtImageCameraInfo.validate_camera_items(self.view)

    def _select_drop_index(self, destination_index: QModelIndex):
        """ Select current row or clear selection """
        if not destination_index.isValid():
            src_model = self.view.model().sourceModel()
            last_index = self.view.editor.match.find_highest_order_index(src_model)

            if not last_index:
                self.view.editor.selection.clear_selection()
                return

            destination_index = last_index

        self.view.selectionModel().setCurrentIndex(destination_index, self.clear_select_current_flags)

    def _paste(self):
        self.view.editor.paste_items(self.clipboard)

    def _copy(self, source_view) -> bool:
        item_copies = source_view.editor.copy_items()

        if not item_copies:
            return False

        self.clipboard.items = item_copies
        self.clipboard.origin = source_view

        return True
