from PySide2.QtCore import QObject, QTimer, Qt, Signal
from PySide2.QtWidgets import QUndoCommand

from modules.itemview.model import KnechtModel, KnechtSortFilterProxyModel
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.itemview.tree_view_utils import setup_header_layout
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class _ViewReplaceModelUndo(QObject):
    def __init__(self, view):
        super(_ViewReplaceModelUndo, self).__init__()
        self.view = view
        self.current_model = view.model()

    def _get_current_src_model(self):
        try:
            return self.current_model.sourceModel()
        except AttributeError as e:
            LOGGER.debug('Error accessing view source model: %s', e)
            return None

    def change_model(self, new_model):
        if not self.current_model or not self.current_model.rowCount():
            # Previous model was empty
            return False

        undo_cmd = _ViewChangeModelCmd(self.view, self.current_model, new_model)
        self.view.undo_stack.push(undo_cmd)
        self.view.undo_stack.setActive(True)
        return True


class _ViewChangeModelCmd(QUndoCommand):
    def __init__(self, view, current_model, new_model):
        """

        :param view:
        :param current_model:
        :param new_model:
        :param model_changed_signal: Signal to emit as True when model updated(redo) or False on undo
        """
        super(_ViewChangeModelCmd, self).__init__()
        self.view = view
        self.current_model = current_model
        self.new_model = new_model

    def redo(self):
        self.view.setModel(self.new_model)

        # Set undo text
        self.setText(_('Bauminhalte wiederherstellen.'))

    def undo(self):
        self.view.setModel(self.current_model)

        # Set redo text
        self.setText(_('Bauminhalte verwerfen.'))


class UpdateModel(QObject):
    finished = Signal()

    def __init__(self, view):
        """ Update the model of provided view. Undoable. Optional target to inform of update via Signal.

        :param modules.itemview.tree_view.KnechtTreeView view: Tree View to update
        :param model_updated_callback: optional Target to emit Signal(bool) to when model update re-/undone (True/False)
        """
        super(UpdateModel, self).__init__(parent=view)
        self.view = view
        self.progress_bar = None

    def update(self, new_model: KnechtModel):
        """
            Creates a QSortFilterProxyModel for the provided model and updates the view model with the
            proxy model instead of the actual model.

            If the previous model contained data, it will create an Undo command.
        """
        view_undo = _ViewReplaceModelUndo(self.view)

        self.view.progress_msg.msg(_('Daten werden eingerichtet.'))
        self.view.progress_msg.show_progress()

        new_model.silent = False

        proxy_model = KnechtSortFilterProxyModel(self.view)
        proxy_model.setSourceModel(new_model)

        if not view_undo.change_model(proxy_model):
            # Previous model was empty, no undo created
            # We need to update the model without undo
            self.view.setModel(proxy_model)

        QTimer.singleShot(1, self.setup_header)

    def setup_header(self):
        setup_header_layout(self.view)
        QTimer.singleShot(1, self.sort_model)

    def sort_model(self):
        self.view.sortByColumn(Kg.ORDER, Qt.AscendingOrder)
        self.exit()

    def exit(self):
        self.view.progress_msg.hide_progress()
        self.view.refresh()

        LOGGER.debug('Model update finished for: %s', self.view.objectName())
        self.finished.emit()

        self.setParent(None)
        self.view = None
        self.deleteLater()
