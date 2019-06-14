from PySide2 import QtWidgets, QtCore

from modules.gui.ui_resource import IconRsc
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


def add_context_action(menu, action_call, icon, desc='Description',
                       inactive_widgets=list(), active_widgets=list(),
                       action_parent=None):
    if not action_parent:
        action_parent = menu

    new_action = QtWidgets.QAction(desc, action_parent)

    if icon:
        new_action.setIcon(icon)

    new_action.triggered.connect(action_call)

    action_parent.addAction(new_action)

    # Black or White Filter context functionality to certain widgets
    if active_widgets:
        new_action.setEnabled(False)
    elif inactive_widgets:
        new_action.setEnabled(True)

    if menu.parent in inactive_widgets:
        new_action.setEnabled(False)

    if menu.parent in active_widgets:
        new_action.setEnabled(True)

    return new_action


class JobManagerContextMenu(QtWidgets.QMenu):
    cancel_job = QtCore.Signal(object)
    move_job = QtCore.Signal(object, bool)
    force_psd = QtCore.Signal(object)

    def __init__(self, widget, ui):
        super(JobManagerContextMenu, self).__init__(widget)
        self.widget, self.ui = widget, ui

        add_context_action(self, self.cancel_job_item, IconRsc.get_icon('close'),
                           desc=_('Job abbrechen'))
        add_context_action(self, self.force_psd_creation, IconRsc.get_icon('reset_state'),
                           desc=_('PSD Erstellung erzwingen.'))
        add_context_action(self, self.open_output_dir, IconRsc.get_icon('folder'),
                           desc=_('Ausgabe Verzeichnis öffnen'))
        add_context_action(self, self.remove_render_file, IconRsc.get_icon('trash'),
                           desc=_('Maya Rendering Szene löschen'))
        add_context_action(self, self.move_job_top, IconRsc.get_icon('options'),
                           desc=_('An den Anfang der Warteschlange'))
        add_context_action(self, self.move_job_back, IconRsc.get_icon('options'),
                           desc=_('An das Ende der Warteschlange'))

        self.widget.installEventFilter(self)

    def get_item(self):
        if len(self.widget.selectedItems()) > 0:
            return self.widget.selectedItems()[0]

    def cancel_job_item(self):
        item = self.get_item()

        if item:
            self.cancel_job.emit(item)

    def force_psd_creation(self):
        item = self.get_item()

        if item:
            self.force_psd.emit(item)

    def open_output_dir(self):
        item = self.get_item()

        if item:
            self.widget.manager_open_item(item)

    def remove_render_file(self):
        item = self.get_item()

        if item:
            self.widget.manager_delete_render_file(item)

    def move_job_top(self):
        self.__move_job(True)

    def move_job_back(self):
        self.__move_job(False)

    def __move_job(self, to_top):
        item = self.get_item()

        if item:
            self.move_job.emit(item, to_top)

    def eventFilter(self, obj, event):
        if obj is self.widget:
            if event.type() == QtCore.QEvent.ContextMenu:
                self.popup(event.globalPos())
                return True

        return False
