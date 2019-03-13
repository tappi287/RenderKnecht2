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

    def __init__(self, ui, widget: QWidget):
        """

        :param modules.gui.main_ui.KnechtWindow ui: Knecht main window
        :param widget: widget to display as tab widget
        """
        super(GenericTabWidget, self).__init__(ui)
        self.ui = ui

        if widget.windowTitle():
            self.name = widget.windowTitle()
        else:
            self.name = 'Tab Dialog'

        # Add widget to this tab widget
        self.widget = widget

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(widget)

        self.setLayout(layout)

        # Add tab and make current
        self.index = self.ui.view_mgr.tab.addTab(self, self.name)
        self.ui.view_mgr.tab.setCurrentIndex(self.index)

        self.org_widget_close_event = self.widget.closeEvent

    def close_event_wrapper(self, event):
        self.org_widget_close_event(event)

        if event.isAccepted():
            LOGGER.debug('TabIndex(%s) child widget was closed', self.index)
