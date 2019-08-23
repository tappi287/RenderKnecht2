from pathlib import Path
from typing import Union, Tuple, List

from PySide2.QtCore import QObject, Qt, Signal, Slot
from PySide2.QtWidgets import QApplication, QLineEdit, QTabWidget, QTreeView, QVBoxLayout, QWidget, QUndoGroup

from modules.gui.gui_utils import replace_widget
from modules.itemview.model import KnechtModel
from modules.itemview.model_update import UpdateModel
from modules.itemview.tree_view import KnechtTreeView
from modules.itemview.tree_view_utils import KnechtTreeViewShortcuts, setup_header_layout
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class ViewFileManager:
    def __init__(self, view_mgr):
        """ Keeps track of tree views, their tab widgets and associated files """
        self.view_mgr: ViewManager = view_mgr

        # FilePath: tabPage
        self.files = list()
        self.widgets = list()

    def update(self, file: Path, widget: QWidget, add: bool):
        if not file:
            return

        if not add:
            if file not in self.files:
                return

            idx = self.widgets.index(widget)
            self.files.pop(idx)
            self.widgets.pop(idx)
        elif add:
            if widget in self.widgets:
                # Update existing entry
                idx = self.widgets.index(widget)
                self.files[idx] = file
                return

            self.files.append(file)
            self.widgets.append(widget)

    def current_file(self) -> Union[None, Path]:
        current_widget = self.view_mgr.tab.currentWidget()
        if current_widget not in self.widgets:
            return

        idx = self.widgets.index(current_widget)
        return self.get_ls_item(self.files, idx)

    def get_file_from_widget(self, current_widget) -> Union[None, Path]:
        if current_widget not in self.widgets:
            return

        idx = self.widgets.index(current_widget)

        return self.get_ls_item(self.files, idx)

    def get_widget_from_file(self, file: Path) -> Union[None, Path]:
        if file not in self.files:
            return

        idx = self.files.index(file)

        return self.get_ls_item(self.widgets, idx)

    @Slot(QWidget)
    def remove_widget(self, widget):
        self.widget_about_to_be_destroyed(widget)

    def widget_about_to_be_destroyed(self, obj):
        """ Remove widgtes that are about to be destroyed """
        if obj not in self.widgets:
            return

        idx = self.widgets.index(obj)
        file = self.files[idx]
        LOGGER.info('Removing tab widget from file_mgr - %s, %s', file.name, obj.objectName())
        self.update(file, obj, False)

    def already_open(self, file: Path):
        file = Path(file)

        if file not in self.files:
            return False

        self._already_open_action(file)
        return True

    def _already_open_action(self, file):
        """ Point the user to the already opened file """
        current_widget = self.get_widget_from_file(file)

        if not current_widget:
            self.view_mgr.ui.msg(_('Fehler - Kann bereits geöffnete Datei nicht in Tabulatoren finden.'), 5000)
            return

        self.view_mgr.tab.setCurrentWidget(current_widget)
        self.view_mgr.ui.msg(_('Datei ist bereits geöffnet.'), 5000)

    @staticmethod
    def get_ls_item(ls: list, idx: int) -> Union[None, Path, QWidget]:
        if idx >= len(ls):
            return None
        return ls[idx]


class ViewManager(QObject):
    view_updated = Signal(KnechtTreeView)

    file_update = Signal(Path, QWidget, bool)
    widget_about_to_be_removed = Signal(QWidget)  # Used to inform the file manager

    view_about_to_be_removed = Signal(KnechtTreeView)  # Not used internally, use from outside

    is_initial_load = True

    def __init__(self, tab_widget, undo_group: QUndoGroup, filter_widget: QLineEdit=None):
        """ Manages tab widgets containing document tree views

        :param tab_widget: The tab widget to manage
        :param undo_group: Undo Group to create tree views with
        :param filter_widget: Filter QLineEdit to set as filter widget for new views
        """
        super(ViewManager, self).__init__()
        self.tab: QTabWidget = tab_widget

        self.filter_widget = filter_widget
        self.undo_grp = undo_group

        # File manager, remembers View/File association
        self.file_mgr = ViewFileManager(self)
        self.file_update.connect(self.file_mgr.update)
        self.widget_about_to_be_removed.connect(self.file_mgr.remove_widget)

        # Setup tab Signals
        self.tab.tabCloseRequested.connect(self._remove_view_tab)
        self.tab.currentChanged.connect(self._tab_changed)

        self.tab.currentWidget().destroyed.connect(self.file_mgr.widget_about_to_be_destroyed)

    def replace_tree_view(self, tree_view: QTreeView) -> KnechtTreeView:
        """ Replace the UI Designer placeholder tree views """
        parent = tree_view.parent()
        new_view = KnechtTreeView(parent, self.undo_grp)
        replace_widget(tree_view, new_view)

        return new_view

    def create_view(self, new_model: KnechtModel, file: Path, new_page: bool=False) -> QTreeView:
        """ Creates a new tab page and tree view or update untouched empty views
        """
        # Try to update existing empty tab page
        if not new_page and self._update_existing_page(new_model, file):
            self.view_updated.emit(self.current_view())
            self.widget_about_to_be_removed.emit(self.tab.currentWidget())
            self.file_update.emit(file, self.tab.currentWidget(), True)
            return self.current_view()

        # Create new tab page
        new_page = self._add_tab_page(new_model, file)
        self.view_updated.emit(new_page.user_view)
        self.file_update.emit(file, new_page, True)
        return new_page.user_view

    def _update_existing_page(self, new_model, file: Path):
        current_view = self.current_view()

        if not current_view.undo_stack.isClean():
            return False

        if not current_view.model().sourceModel().rowCount():
            if new_model:
                update_model = UpdateModel(current_view)
                update_model.update(new_model)

            self.update_tab_title(self.tab.currentIndex(), file)
            current_view.setObjectName(file.name)
            current_view.undo_stack.clear()
            setup_header_layout(current_view)
            return True

        return False

    def _add_tab_page(self, new_model: KnechtModel, file: Path) -> QWidget:
        new_page = self._create_tab_page()
        self.tab.addTab(new_page, file.name)

        self.setup_tree_view(new_page.user_view, new_model, file, self.filter_widget)

        self.tab.setCurrentWidget(new_page)
        self.update_tab_title(self.tab.currentIndex(), file)
        setup_header_layout(new_page.user_view)

        return new_page

    def update_tab_title(self, tab_idx, file, clean: bool = True):
        if file is None:
            file = Path('New_Document.xml')

        title = file.name
        if not clean:
            title = f'*{file.name}*'

        self.tab.setTabText(tab_idx, title)
        self.tab.setTabToolTip(tab_idx, file.as_posix())

    def _create_tab_page(self):
        new_page = QWidget()
        new_page.destroyed.connect(self.file_mgr.widget_about_to_be_destroyed)
        new_view = KnechtTreeView(new_page, self.undo_grp)

        new_page.user_view = new_view

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(new_view)

        new_page.setLayout(layout)
        return new_page

    def reject_tab_remove(self):
        pass

    def ask_on_close(self, tab_view) -> bool:
        return True

    def _remove_view_tab(self, index):
        QApplication.processEvents()

        tab_to_remove = self.tab.widget(index)
        if not tab_to_remove or hasattr(tab_to_remove, 'none_document_tab'):
            return

        tab_view = tab_to_remove.user_view

        if not tab_view.undo_stack.isActive() and not tab_view.undo_stack.isClean():
            # Undo in progress
            self.reject_tab_remove()
            return

        if not tab_view.editor.enabled:
            self.reject_tab_remove()
            return

        if not self.ask_on_close(tab_view):
            return

        # Remove Render Presets of this view
        self.view_about_to_be_removed.emit(tab_view)

        # Remove File entries
        self.widget_about_to_be_removed.emit(tab_to_remove)

        tab_to_remove.deleteLater()
        self.tab.removeTab(index)

    def _tab_changed(self, index):
        """
            Trigger a menu + undo_stack update on tab changed
            Making sure user interacts with the displayed view
            even if he has not yet focused the view itself
        """
        current_tab = self.tab.widget(index)
        if hasattr(current_tab, 'none_document_tab'):
            return

        current_view = current_tab.user_view
        self.log_tabs()

        # Update view filtering
        current_view.set_filter_widget_text(current_view.current_filter_text())

    def current_tab_is_document_tab(self):
        if hasattr(self.current_tab(), 'none_document_tab'):
            return False
        return True

    def current_tab(self) -> QWidget:
        return self.tab.currentWidget()

    def current_view(self) -> KnechtTreeView:
        """ Guarantees to return a KnechtTreeView even if the current tab is a non-document widget """
        current_tab = self.tab.currentWidget()

        if not hasattr(current_tab, 'user_view'):
            # Look for existing tab with tree view
            for i in range(self.tab.count() - 1, -1, -1):
                if hasattr(self.tab.widget(i), 'user_view'):
                    self.tab.setCurrentIndex(i)
                    return self.tab.widget(i).user_view

            # Create a tab with a view if necessary
            model = KnechtModel()
            return self.create_view(model, Path('New_Document_View.xml'), new_page=True)
        return current_tab.user_view

    def current_file(self) -> Path:
        """ Guarantees to return the file of the current document view """
        tab_idx = self.get_tab_index_by_view(self.current_view())
        return self.file_mgr.get_file_from_widget(self.tab.widget(tab_idx))

    def setup_tree_view(self,
                        tree_view: KnechtTreeView, model: Union[KnechtModel, None] = None,
                        file: Path = Path('New_Document.xml'), filter_widget: QLineEdit=None):
        # Setup TreeView model
        if not model:
            # Use empty model if none provided
            model = KnechtModel()

        # Setup model
        update_model = UpdateModel(tree_view)
        update_model.update(model)
        tree_view.progress.hide()

        # Setup keyboard shortcuts
        shortcuts = KnechtTreeViewShortcuts(tree_view)
        tree_view.shortcuts = shortcuts

        # Setup filter text widget
        if filter_widget:
            tree_view.filter_text_widget = filter_widget

        # Set Tree object name
        tree_view.setObjectName(file.name)

        # Set focus to the just created view
        # otherwise menus may try to access already deleted views
        tree_view.setFocus(Qt.OtherFocusReason)

        # Connect view clean status change
        tree_view.clean_changed.connect(self.view_clean_changed)

        LOGGER.debug('View manager basic tree setup for %s %s', tree_view.objectName(), file.name)

        self.additional_tree_setup(tree_view)

    def additional_tree_setup(self, tree_view: KnechtTreeView):
        pass

    def view_clean_changed(self, clean: bool, view):
        LOGGER.debug('Tree View clean state changed: %s %s', clean, view.objectName())
        tab_idx = self.get_tab_index_by_view(view)
        file = self.file_mgr.get_file_from_widget(self.tab.widget(tab_idx))

        self.update_tab_title(tab_idx, file, clean)

    def get_tab_index_by_view(self, view):
        for tab_idx in range(0, self.tab.count()):
            tab_page = self.tab.widget(tab_idx)

            if not hasattr(tab_page, 'user_view'):
                continue

            if tab_page.user_view is view:
                break
        else:
            tab_idx = 0

        return tab_idx

    def get_view_by_file(self, file: Path):
        return self.file_mgr.get_widget_from_file(file).user_view

    def get_view_by_name(self, name: str) -> Union[None, QWidget]:
        for (tab_idx, tab_page, file) in self._list_tabs():
            if self.tab.tabText(tab_idx) == name:
                return tab_page

    def _list_tabs(self) -> Tuple[int, QWidget, str]:
        for tab_idx in range(0, self.tab.count()):
            tab_page = self.tab.widget(tab_idx)
            file = self.file_mgr.get_file_from_widget(tab_page)

            if not file:
                file = 'No file set.'
            else:
                file = file.name

            yield tab_idx, tab_page, file

    def log_tabs(self):
        """ Debug fn """

        def get_tab_view_name(tab):
            if not tab:
                return 'NONE'
            if hasattr(tab_page, 'view'):
                return tab_page.view.objectName()
            else:
                return tab_page.objectName()

        LOGGER.debug('##### Tab Index #####')
        for (tab_idx, tab_page, file) in self._list_tabs():
            LOGGER.debug('{:02d} {} - {}'.format(tab_idx, get_tab_view_name(tab_page), file))

        LOGGER.debug('##### File Mgr Index #####')
        for idx, file in enumerate(self.file_mgr.files):
            if not file:
                continue
            tab_page = self.file_mgr.get_widget_from_file(file)
            LOGGER.debug('{:02d} {} - {}'.format(idx, get_tab_view_name(tab_page), file.name))
