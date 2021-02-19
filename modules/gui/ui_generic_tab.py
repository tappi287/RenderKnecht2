from PySide2.QtCore import Slot
from PySide2.QtWidgets import QVBoxLayout, QWidget

from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class GenericTabWidget(QWidget):
    none_document_tab = True

    def __init__(self, ui, widget: QWidget, name: str=''):
        """ Creates a tab inside ui containing widget

        :param modules.gui.main_ui.KnechtWindow ui: Knecht main window
        :param widget: widget to display as tab widget
        """
        super(GenericTabWidget, self).__init__(ui)
        self.ui = ui
        self.name = widget.windowTitle()
        if name:
            self.name = name

        # Add widget to this tab widget
        self.widget = widget

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(widget)

        self.setLayout(layout)

        # Add tab and make current
        index = self.ui.view_mgr.tab.insertTab(0, self, self.name)
        self.ui.view_mgr.tab.setCurrentIndex(index)
        self.ui.view_mgr.tab.tabCloseRequested.connect(self.tab_close_request)

        self.org_widget_close_event = self.widget.closeEvent
        self.widget.closeEvent = self.close_event_wrapper

    @Slot(int)
    def tab_close_request(self, index):
        # Update index
        own_index = self.ui.view_mgr.tab.indexOf(self)

        if index != own_index:
            return

        # Forward tab close request to widget
        self.widget.close()
        self.widget.deleteLater()

    def close_event_wrapper(self, event):
        self.org_widget_close_event(event)

        own_index = self.ui.view_mgr.tab.indexOf(self)

        if event.isAccepted():
            LOGGER.debug('TabIndex %s child widget was closed', own_index)
            self.ui.view_mgr.tab.removeTab(own_index)
            self.deleteLater()
