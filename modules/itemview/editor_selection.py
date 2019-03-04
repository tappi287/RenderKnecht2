from bisect import bisect
from typing import Tuple, List

from PySide2.QtCore import QModelIndex, QObject, Slot
from PySide2.QtWidgets import QTreeView

from modules.itemview.model import KnechtModel
from modules.log import init_logging

LOGGER = init_logging(__name__)


class KnechtItemSelection(QObject):
    """
        View Editor helper class to find current view model and selections
    """
    def __init__(self, editor):
        super(KnechtItemSelection, self).__init__(editor)
        self.editor = editor
        self.whole_tree_selected = False

    @property
    def view(self) -> QTreeView:
        return self.editor.view

    def get_current_selection(self) -> Tuple[QModelIndex, KnechtModel]:
        """ Return the current selected element and the actual source model """
        src_model = self.view.model().sourceModel()

        proxy_model = self.view.model()
        proxy_index = self.view.selectionModel().currentIndex()

        src_index = proxy_model.mapToSource(proxy_index)

        # Return Index mapped to source model and source model
        return src_index, src_model

    def _get_selection(self) -> Tuple[List[QModelIndex], List[QModelIndex], KnechtModel]:
        """ Return all selected elements[in proxy sort order] and the actual source model"""
        self.whole_tree_selected = False
        try:
            src_model = self.view.model().sourceModel()
        except AttributeError:
            LOGGER.error('Error accessing proxy model while getting selection.')
            return [], [], self.view.model()

        proxy_model = self.view.model()
        proxy_index_ls = self.view.selectionModel().selectedRows()

        src_index_ls = []
        for proxy_index in proxy_index_ls:
            src_index_ls.append(proxy_model.mapToSource(proxy_index))

        sub_items, top_items = self.sort_index_list(src_index_ls)

        if src_model.rowCount() == len(top_items):
            # Report the whole model as selected
            self.whole_tree_selected = True
            return sub_items, top_items, src_model

        # Return selected source model indices and the source model
        return sub_items, top_items, src_model

    def get_selection(self) -> Tuple[List[QModelIndex], KnechtModel]:
        """ Return all selected elements[in proxy sort order] and the actual source model

        :returns Tuple[List[QModelIndex], KnechtModel]: list of selected items, child items first, then top level items
                                                        and the actual source model
        """

        sub_items, top_items, src_model = self._get_selection()
        return sub_items + top_items, src_model

    def get_selection_top_level(self) -> Tuple[List[QModelIndex], KnechtModel]:
        _, top_items, src_model = self._get_selection()
        return top_items, src_model

    def highlight_invalid_references(self):
        src_model = self.view.model().sourceModel()
        prx_model = self.view.model()

        invalid_ref_idx_ls = src_model.id_mgr.get_invalid_references_indices(prx_model)
        self.clear_and_select_proxy_index_ls(invalid_ref_idx_ls)

    def highlight_recursive_indices(self):
        src_model = self.view.model().sourceModel()
        prx_model = self.view.model()

        recursive_idx_ls = src_model.id_mgr.get_recursive_indices(prx_model)
        self.clear_and_select_proxy_index_ls(recursive_idx_ls)

    def highlight_selection(self):
        """ Scroll to selected items and expand parents of selected child items """
        src_index_ls, _ = self.get_selection()
        current_src_index, _ = self.get_current_selection()
        src_index_ls.append(current_src_index)

        prx_index_ls = list()
        for idx in src_index_ls:
            prx_idx = self.view.model().mapFromSource(idx)
            prx_index_ls.append(prx_idx)

        self.clear_and_select_proxy_index_ls(prx_index_ls)

    def select_references(self):
        src_index_ls, src_model = self.get_selection()

        if not src_index_ls:
            return

        get_ref = src_model.id_mgr.get_references_by_indices

        preset_idx_ls, reference_idx_ls = get_ref(src_index_ls, proxy_model=self.view.model())
        prx_index_ls = reference_idx_ls + preset_idx_ls

        if not prx_index_ls:
            return

        self.clear_and_select_proxy_index_ls(prx_index_ls)

    def clear_selection(self):
        selection = self.view.selectionModel()
        selection.clearSelection()
        selection.setCurrentIndex(QModelIndex(), selection.Clear)

    def clear_and_select_proxy_index_ls(self, prx_index_ls):
        """ Clear selection and select and expand every item in the
            provided list of proxy indices.
        """
        selection = self.view.selectionModel()
        selection.clearSelection()

        for proxy_index in prx_index_ls:
            LOGGER.debug('Selecting and expanding prx idx: @%03dP%03d', proxy_index.row(), proxy_index.parent().row())
            selection.select(proxy_index, selection.Select | selection.Rows)
            self.scroll_to_index(proxy_index)

            self.expand_parent_index(proxy_index)

    def clear_and_select_src_index_ls(self, src_index_ls):
        """ Clear selection and select and expand every item in the
            provided list of proxy indices.
        """
        selection = self.view.selectionModel()
        selection.clearSelection()

        for src_index in src_index_ls:
            LOGGER.debug('Selecting and expanding src idx: @%03dP%03d', src_index.row(), src_index.parent().row())
            prx_index = self.view.model().mapFromSource(src_index)
            selection.select(prx_index, selection.Select | selection.Rows)
            self.scroll_to_index(prx_index)

            self.expand_parent_index(prx_index)

    @Slot(QModelIndex)
    def expand_parent_index(self, proxy_index: QModelIndex):
        LOGGER.debug('Expanding row @%03d', proxy_index.parent().row())
        if not self.view.isExpanded(proxy_index.parent()):
            self.view.expand(proxy_index.parent())

    def clear_and_set_current(self, current_idx: QModelIndex=QModelIndex()):
        self.clear_selection()
        selection = self.view.selectionModel()
        selection.setCurrentIndex(current_idx, selection.Select | selection.Rows)
        selection.select(current_idx, selection.Select | selection.Rows)

    def scroll_to_index(self, proxy_index: QModelIndex):
        self.view.scrollTo(proxy_index, self.view.PositionAtCenter)

    @staticmethod
    def sort_index_list(index_ls) -> Tuple[list, list]:
        top_rows, top_ls = list(), list()
        sub_rows, sub_ls = list(), list()

        for index in index_ls:
            row = index.row()

            if not index.parent().isValid():
                top_rows.append(row)
                insert_idx = len(top_rows) - bisect(sorted(top_rows), row)
                top_ls.insert(insert_idx, index)
            else:
                sub_rows.append(row)
                insert_idx = len(sub_rows) - bisect(sorted(sub_rows), row)
                sub_ls.insert(insert_idx, index)

        return sub_ls, top_ls
