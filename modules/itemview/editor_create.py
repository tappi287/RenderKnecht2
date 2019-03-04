from typing import List, Iterator

from PySide2.QtCore import Qt, QObject, QModelIndex
from PySide2.QtWidgets import QTreeView

from modules.gui.clipboard import TreeClipboard
from modules.idgen import KnechtUuidGenerator as Kid
from modules.itemview.editor_undo import TreeCommand, TreeChainCommand
from modules.itemview.item import KnechtItem
from modules.itemview.model import KnechtModel
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.log import init_logging

LOGGER = init_logging(__name__)


class KnechtEditorCopyPaste(QObject):
    """ KnechtEditor Extension to copy to and paste from the ui clipboard """
    preset_creation_accepted_types = [Kg.preset, Kg.variant, Kg.reference]

    def __init__(self, editor):
        """ View model editor Copy & Paste extensions

        :param modules.itemview.editor.KnechtEditor editor:
        """
        super(KnechtEditorCopyPaste, self).__init__(editor)
        self.editor = editor

    @property
    def view(self) -> QTreeView:
        return self.editor.view

