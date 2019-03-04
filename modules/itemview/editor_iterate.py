from typing import Iterator, Tuple, Generator
from PySide2.QtCore import QModelIndex, Qt

from modules.itemview.item import KnechtItem
from modules.itemview.model_globals import KnechtModelGlobals as KG
from modules.log import init_logging

LOGGER = init_logging(__name__)


class KnechtIterateView:
    """
        View Editor helper class to iterate the model
    """
    debug = False

    def __init__(self, editor):
        self.editor = editor

    @property
    def view(self):
        return self.editor.view

    def order_items(self, parent: QModelIndex=QModelIndex()):
        self.rewrite_order_column(parent)

    def iterate_view(self, parent: QModelIndex=QModelIndex(), column: int=None
                     ) -> Tuple[QModelIndex, KnechtItem]:
        """
        Iterate all items in the view model under the provided parent. If no parent provided, all top level
        items under the root item will be iterated.

        :param parent: QModelIndex of the parent item which children will be iterated
        """
        src_model = self.view.model().sourceModel()
        parent_item = src_model.get_item(parent)
        proxy_parent = self.view.model().mapFromSource(parent)
        column = column or KG.ORDER

        for row in range(parent_item.childCount()):
            index = self.view.model().index(row, column, proxy_parent)

            src_index = self.view.model().mapToSource(index)

            yield src_index, src_model.get_item(src_index)

    def rewrite_order_column(self, parent: QModelIndex):
        row_num = 0

        for src_index, item in self.iterate_view(parent):
            if not item:
                continue

            item.itemData[Qt.DisplayRole][KG.ORDER] = f'{row_num:03d}'
            row_num += 1
