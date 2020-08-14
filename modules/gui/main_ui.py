from pathlib import Path

from PySide2.QtCore import QTimer, Qt, Signal
from PySide2.QtGui import QIcon, QPixmap, QDragEnterEvent, QDropEvent
from PySide2.QtWidgets import QMainWindow, QSystemTrayIcon, QTreeView, QWidget
from PySide2.QtWinExtras import QWinTaskbarButton

from modules.globals import FROZEN, Resource
from modules.gui.clipboard import TreeClipboard
from modules.gui.gui_utils import SetupWidget
from modules.gui.main_menu import MainWindowMenu
from modules.gui.ui_overlay import MainWindowOverlay
from modules.gui.ui_resource import SoundRsc
from modules.gui.ui_translations import translate_main_ui
from modules.gui.ui_view_manager import UiViewManager
from modules.gui.widgets.button_color import QColorButton
from modules.gui.widgets.main_ui_widgets import MainWindowWidgets
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.itemview.tree_view import KnechtTreeView
from modules.knecht_update import KnechtUpdate
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class KnechtWindow(QMainWindow):
    system_tray_click_connected = False
    tree_focus_changed = Signal(QTreeView)
    is_about_to_quit = Signal()

    def __init__(self, app):
        """ The GUI MainWindow Class

        :param modules.gui.main_app.KnechtApp app: Main QApplication class
        """
        super(KnechtWindow, self).__init__()
        self.app = app
        SetupWidget.from_ui_file(self, Resource.ui_paths['knecht_model_gui'],
                                 custom_widgets={'QColorButton': QColorButton})

        self.rk_icon = QIcon(QPixmap(Resource.icon_paths['RK_Icon']))

        # Set version window title
        self.setWindowTitle(
            f'{self.windowTitle()} - v{self.app.version}'
            )

        # ---- Setup Main Menu ----
        self.main_menu = MainWindowMenu(self)

        # ---- Tree Setup ----
        tree_view_list = [self.variantTree, self.renderTree]
        tree_file_list = [_('Variantenbaum'), _('Renderliste')]
        tree_filter_widgets = [self.lineEdit_Var_filter, self.lineEdit_Ren_filter]

        # View Mgr will replace placeholder presetTree
        self.view_mgr = UiViewManager(self, self.presetTree)
        # Set presetTree to current View Mgr view to avoid accessing deleted object
        self.presetTree = self.view_mgr.current_view()

        replaced_views = self.view_mgr.setup_default_views(tree_view_list, tree_file_list, tree_filter_widgets)

        self.variantTree, self.renderTree = replaced_views[0], replaced_views[1]
        for default_view in [self.variantTree, self.renderTree]:
            default_view.setFocusPolicy(Qt.ClickFocus)
            default_view.undo_stack.cleanChanged.disconnect()

        # ---- Setup renderTree ----
        self.renderTree.is_render_view = True
        self.renderTree.accepted_item_types = [Kg.render_preset, Kg.preset]

        # ---- Internal Clipboard ----
        self.clipboard = TreeClipboard()

        # ---- Store last tree with focus ----
        self.last_focus_tree = self.presetTree

        # ---- System tray and taskbar ----
        self.system_tray = QSystemTrayIcon(self.rk_icon, self)
        self.system_tray.hide()

        # ---- Windows taskbar progress indicator ----
        self.taskbar_btn = QWinTaskbarButton(self)
        self.taskbar_progress = self.taskbar_btn.progress()
        # Delayed Taskbar Setup (Main Window needs to be created for correct window handle)
        QTimer.singleShot(1, self.init_taskbar)

        # ---- Generic Info Overlay ----
        self.overlay = MainWindowOverlay(self.centralWidget())

        # ---- Close Action ----
        self.actionBeenden.triggered.connect(self.close)

        # ---- Setup Main UI Widgets ----
        MainWindowWidgets(self)

        # Updater
        self.updater = KnechtUpdate(self)
        self.updater.update_available.connect(self.main_menu.info_menu.update_ready)
        QTimer.singleShot(20000, self.auto_update)  # Initial Update check

        self.app.focusChanged.connect(self.app_focus_changed)

        # ---- Translate Ui elements loaded from ui file ----
        translate_main_ui(self)

        self.setAcceptDrops(True)

    def _get_drop_event_files(self, mime_data):
        files = []
        for url in mime_data.urls():
            if not url.isLocalFile():
                continue

            file = Path(url.toLocalFile())

            if file.suffix.casefold() in self.main_menu.file_menu.supported_file_types:
                files.append(file)

        return files

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            if self._get_drop_event_files(event.mimeData()):
                event.acceptProposedAction()
            else:
                event.ignore()

    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasUrls():
            files = self._get_drop_event_files(event.mimeData())
            if files:
                for file in files:
                    self.main_menu.file_menu.guess_open_file(file)
                event.accept()
                return True

        event.ignore()
        return False

    def app_focus_changed(self, old_widget: QWidget, new_widget: QWidget):
        if isinstance(new_widget, KnechtTreeView):
            self.set_last_focus_tree(new_widget)

    def init_taskbar(self):
        """ Initializes the MS Windows taskbar button"""
        # Needs to be called after window is created/shown
        self.taskbar_btn.setWindow(self.windowHandle())

        self.taskbar_progress.setRange(0, 100)
        self.taskbar_progress.valueChanged.connect(self.taskbar_progress.show)

    def show_tray_notification(self, title: str, message: str, clicked_callback=None):
        if not self.system_tray.isVisible():
            self.system_tray.show()

        # Disconnect existing callback
        if self.system_tray_click_connected:
            try:
                self.system_tray.messageClicked.disconnect()
            except RuntimeError:
                LOGGER.info('Could not disconnect system tray messageClicked handler.')
            finally:
                self.system_tray_click_connected = False

        if clicked_callback is not None:
            self.system_tray.messageClicked.connect(clicked_callback)
            self.system_tray_click_connected = True

        self.system_tray.showMessage(title, message, self.rk_icon)

    def set_last_focus_tree(self, set_tree_focus):
        if isinstance(set_tree_focus, KnechtTreeView):
            self.last_focus_tree = set_tree_focus

        self.tree_focus_changed.emit(self.last_focus_tree)

    def tree_with_focus(self) -> KnechtTreeView:
        """ Return the current or last known QTreeView in focus """
        widget_in_focus = self.focusWidget()

        if isinstance(widget_in_focus, KnechtTreeView):
            self.last_focus_tree = widget_in_focus

        return self.last_focus_tree

    def check_for_updates(self):
        self.updater.run_update()

    def auto_update(self):
        if self.updater.first_run:
            if FROZEN:
                self.check_for_updates()

    def report_missing_reset(self):
        msg = _('Die Varianten enthalten keine Reset Schaltung! Die zu sendenden Varianten '
                'werden mit vorangegangen Schaltungen kollidieren.')

        self.overlay.display(msg, duration=5000, immediate=True)

    def msg(self, txt: str, duration: int=4000) -> None:
        self.statusBar().showMessage(txt, duration)
        self.overlay.display(txt, duration, immediate=True)

    def play_finished_sound(self):
        self._play_sound(SoundRsc.finished)

    def play_confirmation_sound(self):
        self._play_sound(SoundRsc.positive)

    def play_hint_sound(self):
        self._play_sound(SoundRsc.hint)

    def play_warning_sound(self):
        self._play_sound(SoundRsc.warning)

    def _play_sound(self, resource_key):
        try:
            sfx = SoundRsc.get_sound(resource_key, self)
            sfx.play()
        except Exception as e:
            LOGGER.error(e)
