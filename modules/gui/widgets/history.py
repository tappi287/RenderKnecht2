from PySide2.QtCore import QItemSelectionModel, QObject, QTimer, Qt, Signal, Slot
from PySide2.QtGui import QBrush, QColor
from PySide2.QtWidgets import QListWidget, QListWidgetItem, QPushButton, QTabWidget, QTreeView, QUndoGroup, QUndoStack, \
    QWidget

from modules.globals import Resource
from modules.gui.gui_utils import SetupWidget
from modules.gui.ui_view_manager import UiViewManager
from modules.gui.ui_resource import FontRsc, IconRsc
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class TimeMachine(QObject):
    finished = Signal()

    work_timer = QTimer()
    work_timer.setInterval(150)

    def __init__(self, history, stack: QUndoStack, target_idx: int):
        """ Walks across undo indices

        :param DocHistoryWidget history: The history widget to manipulate
        :param QUndoStack stack: Undostack to call
        :param int target_idx: the index to walk too
        """
        super(TimeMachine, self).__init__()
        self.history = history
        self.stack = stack

        if target_idx >= stack.index():
            target_idx += 1

        self.target_idx = target_idx

        self.work_timer.timeout.connect(self.work)
        self.finished.connect(self.history.time_traveler_arrived)

    def start(self):
        LOGGER.debug('----- Time Machine Start @ %s %s', self.target_idx, self.stack.index())
        self.work_timer.start()

    def work(self):
        if self.target_idx == self.stack.index():
            self.finish()
            return

        if not self.stack.isActive():
            return

        if not self.history.view_mgr.current_view().editor.enabled:
            return

        LOGGER.debug('----- Time Machine work @ %s %s', self.target_idx, self.stack.index())

        if self.target_idx < self.stack.index():
            self.stack.undo()
            LOGGER.debug('Time Machine progressing backward. %s %s', self.target_idx, self.stack.index())
        else:
            self.stack.redo()
            LOGGER.debug('Time Machine progressing forward %s %s', self.target_idx, self.stack.index())

    def finish(self):
        LOGGER.debug('----- Time Machine arrived @ %s %s', self.target_idx, self.stack.index())
        self.work_timer.stop()
        self.finished.emit()


class DocHistoryWidget(QWidget):
    disabled_flags = (Qt.ItemIsSelectable | Qt.ItemNeverHasChildren)
    enabled_flags = (Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemNeverHasChildren)

    update_view_timer = QTimer()
    update_view_timer.setSingleShot(100)

    bg_grey = QBrush(QColor(220, 240, 220), Qt.SolidPattern)
    fg_black = QBrush(QColor(20, 20, 20))
    fg_grey = QBrush(QColor(120, 120, 120))

    title = _('Historie')

    def __init__(self, ui, menu_edit):
        """

        :param modules.gui.main_ui.KnechtWindow ui:
        :param modules.widgets.menu_edit.EditMenu menu_edit:
        """
        super(DocHistoryWidget, self).__init__(ui)
        SetupWidget.from_ui_file(self, Resource.ui_paths['knecht_history'])

        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowTitleHint | Qt.WindowSystemMenuHint)
        self.setWindowIcon(IconRsc.get_icon('later'))

        # --- Setup Fields ---
        self.ui = ui
        self.menu_edit = menu_edit

        self.view_mgr: UiViewManager = None
        self.viewList: QListWidget = self.viewList
        self.tab: QTabWidget = self.ui.srcTabWidget
        self.undo_grp: QUndoGroup = ui.app.undo_grp
        self.time_machine = None

        # --- Buttons ---
        self.jumpBtn: QPushButton = self.jumpBtn
        self.jumpBtn.setIcon(IconRsc.get_icon('history'))
        self.jumpBtn.setText(_('Zum gewählten Schritt springen'))
        self.jumpBtn.pressed.connect(self.time_jump)

        self.redoBtn: QPushButton = self.redoBtn
        self.undoBtn: QPushButton = self.undoBtn
        self.redoBtn.setEnabled(False)
        self.undoBtn.setEnabled(False)
        self.redoBtn.setIcon(IconRsc.get_icon('redo'))
        self.redoBtn.setText(_('Schritt Vorwärts'))
        self.undoBtn.setIcon(IconRsc.get_icon('undo'))
        self.undoBtn.setText(_('Schritt Zurück'))
        # Create undo/redo actions from undo_grp
        self.redo = self.undo_grp.createRedoAction(self, 'Redo')
        self.redo.changed.connect(self.undo_action_changed)
        self.undo = self.undo_grp.createUndoAction(self, 'Undo')
        self.undo.changed.connect(self.undo_action_changed)

        self.redoBtn.released.connect(self.redo.trigger)
        self.undoBtn.released.connect(self.undo.trigger)
        self.addActions([self.redo, self.undo])

        # --- Update delay ---
        self.update_view_timer.timeout.connect(self._update_view)

        # --- Connect viewList ---
        self.viewList.itemDoubleClicked.connect(self.time_jump_item_click)

        self.active_stack: QUndoStack = self.undo_grp.activeStack()
        QTimer.singleShot(1, self.delayed_setup)

    def showEvent(self, e):
        self.update_history_view()

    def undo_action_changed(self):
        obj = self.sender()

        if obj == self.redo:
            self.redoBtn.setEnabled(self.redo.isEnabled())
        elif obj == self.undo:
            self.undoBtn.setEnabled(self.undo.isEnabled())

    @Slot()
    def delayed_setup(self):
        """ Setup attributes that require a fully initialized ui"""
        self.view_mgr: UiViewManager = self.ui.view_mgr

        # --- History Change events ----
        # self.undo_grp.activeStackChanged.connect(self.set_active_stack)
        self.view_mgr.view_updated.connect(self.view_focus_changed)
        self.ui.tree_focus_changed.connect(self.view_focus_changed)
        self.undo_grp.indexChanged.connect(self.update_history_view)

    @Slot(QListWidgetItem)
    def time_jump_item_click(self, item):
        self.viewList.setCurrentItem(item, QItemSelectionModel.ClearAndSelect)
        self.time_jump()

    def time_jump(self):
        if not isinstance(self.active_stack, QUndoStack)\
                or not self.active_stack.isActive()\
                or self.active_stack.count() == 0:
            self.ui.msg(_('Zeitreise fehlgeschlagen.'), 4000)
            return

        self.jumpBtn.setEnabled(False)
        self.undoWidget.setEnabled(False)
        self.menu_edit.undo_action_grp.setEnabled(False)

        item = self.viewList.currentItem()
        target_idx = item.data(Qt.UserRole)
        LOGGER.debug('### User wants to travel to idx: %s, Stack idx: %s',
                     target_idx, self.active_stack.index())

        self.time_travel(target_idx)

    def time_travel(self, target_index: int):
        self.time_machine = TimeMachine(self, self.active_stack, target_index)
        self.time_machine.start()

    def time_traveler_arrived(self):
        self.time_machine = None

        self.jumpBtn.setEnabled(True)
        self.undoWidget.setEnabled(True)
        self.menu_edit.undo_action_grp.setEnabled(True)

    @Slot(QTreeView)
    def view_focus_changed(self, view):
        self.set_active_stack(view.undo_stack)
        self.update_title(view)
        self.update_history_view()

    def set_active_stack(self, undo_stack: QUndoStack):
        if isinstance(undo_stack, QUndoStack) and undo_stack is not self.active_stack:
            LOGGER.debug('Setting Active Stack: %s %s', undo_stack, isinstance(undo_stack, QUndoStack))
            undo_stack.setActive(True)
            self.active_stack = undo_stack

    def update_title(self, view):
        file_name = _('Keine Datei')

        if view.objectName():
            file_name = view.objectName()

        self.setWindowTitle(f'{self.title} - {file_name}')

    def update_history_view(self):
        if not self.update_view_timer.isActive():
            self.update_view_timer.start()

    def _update_view(self):
        if self.isHidden():
            return

        if not isinstance(self.active_stack, QUndoStack):
            LOGGER.debug('Invalid UndoStack - cleaning view.')
            self.clean_view()
            return

        if self.active_stack.isClean() and self.active_stack.count() == 0:
            LOGGER.debug('UndoStack untouched - cleaning view.')
            self.clean_view()
            return

        LOGGER.debug('Current Stack Index: %s', self.active_stack.index())

        self.viewList.clear()
        self.populate_list_view()

    def clean_view(self):
        self.viewList.clear()

        origin = QListWidgetItem(_('Keine Historie Einträge'), self.viewList)
        origin.setIcon(IconRsc.get_icon('history'))

    def populate_list_view(self):
        stack = self.active_stack
        ls = self.viewList
        ls.clear()

        undo_idx = max(0, stack.index() - 1)
        redo_idx = stack.index()

        for c in range(0, stack.count()):
            txt = stack.text(c)
            icon = IconRsc.get_icon('history')

            if c == undo_idx:
                icon = IconRsc.get_icon('undo')

            if c == redo_idx:
                icon = IconRsc.get_icon('forward')

            self.create_history_item(c, txt, icon, redo_idx)

        current_item = self.create_current_item(self.disabled_flags)
        self.viewList.insertItem(redo_idx, current_item)

    def create_history_item(self, c: int, txt: str, icon, redo_idx):
        num = c - redo_idx
        if num >= 0:
            num += 1

        item = QListWidgetItem(f'{txt} [{num: 3d}]', self.viewList)
        item.setData(Qt.UserRole, c)
        item.setFlags(self.enabled_flags)
        item.setIcon(icon)

        if num > 0:
            item.setForeground(self.fg_grey)
            item.setFont(FontRsc.italic)

        return item

    def create_current_item(self, flags):
        if self.active_stack.index() == 0:
            txt = _('  0: Geladener Zustand des Dokuments')
        else:
            txt = _('  0: Aktueller Zustand des Dokuments')
        current_item = QListWidgetItem(txt)
        current_item.setForeground(self.fg_black)
        current_item.setBackground(self.bg_grey)
        current_item.setFlags(flags)
        current_item.setIcon(IconRsc.get_icon('options'))
        return current_item
