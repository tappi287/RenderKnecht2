from PySide2.QtCore import QObject, Qt, QEvent, Signal
from PySide2.QtWidgets import QHeaderView

from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


def setup_header_layout(widget, maximum_width: int=850):
    # Auto resize slows down/triggers too many tree events
    # We stick with default section sizes and resize to content upon user request
    header = widget.header()
    header.setSectionResizeMode(0, QHeaderView.Interactive)
    header.resizeSection(0, 110)

    widget_width = max(100, widget.width())
    oversize_width = 0

    # First pass calculate complete oversized width if every item text would be visible
    for column in range(1, header.count() - 1):
        header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        column_width = header.sectionSize(column) + 40
        oversize_width += column_width

    # Add last and first column width
    oversize_width += header.sectionSize(header.count()) + header.sectionSize(0)

    # Calculate scale factor needed to fit columns inside visible area
    column_scale_factor = max(1, widget_width) / max(1, oversize_width)

    for column in range(1, header.count() - 1):
        width = min((header.sectionSize(column) * column_scale_factor), maximum_width)
        header.setSectionResizeMode(column, QHeaderView.Interactive)
        header.resizeSection(column, width)


class KnechtTreeViewShortcuts(QObject):
    filter_keys = [Qt.Key_Space, Qt.Key_Underscore, Qt.Key_Minus]

    def __init__(self, view):
        """

        :param modules.itemview.tree_view.KnechtTreeView view: View to install shortcuts on
        """
        super(KnechtTreeViewShortcuts, self).__init__(parent=view)
        self.view = view

        self.view.installEventFilter(self)

    def eventFilter(self, obj, event):
        """ Set Knecht Tree View keyboard Shortcuts """
        if not obj or not event:
            return False

        if event.type() != QEvent.KeyPress:
            return False

        if event.key() in (Qt.Key_Backspace, Qt.Key_Escape):  # Backspace clears filter
            self.view.clear_filter()
            return True

        # Send alphanumeric keys to LineEdit filter widget
        if event.text().isalnum() or event.key() in self.filter_keys:
            filter_txt = self.view.current_filter_text()
            filter_txt += event.text()

            self.view.set_filter_widget_text(filter_txt)
            return True

        return False
