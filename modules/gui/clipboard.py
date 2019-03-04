from typing import List

from modules.itemview.item import KnechtItem


class TreeClipboard:
    """ Stores KnechtItem copies and the tree view origin """
    def __init__(self, items: List[KnechtItem]=list(), origin=None):
        """ Can store KnechtItem copies and the origin view

        :param List[KnechtItem] items: list of item copies
        :param Union[KnechtTreeView, None] origin: the source view of the item copies
        """
        self.items: List[KnechtItem] = items
        self.origin = origin

    def clear(self):
        """ Clear the clipboard contents """
        self.items = list()
        self.origin = None
