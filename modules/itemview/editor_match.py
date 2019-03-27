from typing import List, Tuple

from PySide2.QtCore import QModelIndex, Qt

from modules.itemview.model import KnechtModel
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.log import init_logging

LOGGER = init_logging(__name__)


class KnechtMatchItems:
    """
        View Editor helper class to find items inside the proxy model
    """
    def __init__(self, editor):
        self.editor = editor

    @property
    def view(self):
        return self.editor.view

    def index(self, value: str, column: int=0,
              parent: QModelIndex=QModelIndex(), match_flags=Qt.MatchExactly):
        """ Match and return first match """
        match = self._match(value, column, 1, parent, match_flags)

        if not match:
            return QModelIndex()

        return match[-1]

    def indices(self, value: str, column: int=0,
                parent: QModelIndex=QModelIndex(), match_flags=Qt.MatchExactly):
        """ Match and return all matches """
        return self._match(value, column, -1, parent, match_flags)

    def _match(self, value: str, column: int=0, hits: int= -1,
               parent: QModelIndex=QModelIndex(), match_flags=Qt.MatchExactly) -> List[QModelIndex]:
        """
            Matches items in column starting at row 0 of the parent index
            hits defines hw many matches to return; -1 means all
            match_flags can define eg. recursive search, wildcard search or a combination of those
        """
        src_model = self.view.model().sourceModel()
        proxy_model = self.view.model()

        if parent.model() is proxy_model:
            parent = proxy_model.mapToSource(parent)

        match_idx = src_model.index(0, column, parent)
        LOGGER.debug('Match index: @%03dP%03d', match_idx.row(), match_idx.parent().row())

        matches = proxy_model.match(
                    match_idx, Qt.EditRole, value, hits,
                    flags=match_flags
                    )

        return matches

    def find_highest_order_index(self, proxy_model, parent_idx: QModelIndex=QModelIndex()) -> QModelIndex:
        highest_order = proxy_model.rowCount(parent_idx) - 1
        last_index = self.index(f'{highest_order:03d}', Kg.ORDER, parent_idx)

        if not last_index:
            return QModelIndex()

        return last_index

    def find_move_order(self, destination_idx, destination_src_idx: QModelIndex,
                        proxy_model, src_model: KnechtModel) -> int:
        """ From the destination index determine the order value
            to move to. Either order value of the targeted item or
            in case of an invalid index, an order value behind all
            items.
        """
        order = 0

        if not destination_src_idx.isValid():
            last_index = self.find_highest_order_index(proxy_model, destination_idx.parent())

            if last_index.isValid():
                target_src_index = proxy_model.mapToSource(last_index)
                item = src_model.get_item(target_src_index)
                order = int(item.data(Kg.ORDER))
        else:
            item = src_model.get_item(destination_src_idx)
            order = int(item.data(Kg.ORDER))

        return order

    @staticmethod
    def move_direction(destination_order: int, index: QModelIndex, src_model: KnechtModel) -> Tuple[bool, bool]:
        """ Determine if the index should be moved one order below.
            If True the index_below needs to be moved one order up instead of
            altering the move index.
            :returns Tuple[bool, bool]: item is moved one down, item is moved up
        """
        move_one_below, move_up = False, False
        index = src_model.sibling(index.row(), Kg.ORDER, index)  # Make sure to read order column
        current_order = int(index.data())

        if current_order + 1 == destination_order:
            move_one_below = True
        elif current_order > destination_order:
            move_up = True

        return move_one_below, move_up
