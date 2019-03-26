from pathlib import Path
from typing import List

from PySide2.QtCore import Qt, Slot
from PySide2.QtWidgets import QLineEdit

from modules.gui.widgets.menu_tree_context import TreeContextMenu
from modules.gui.widgets.message_box import AskToContinue
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.itemview.tree_view import KnechtTreeView
from modules.itemview.view_manager import ViewManager
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class UiViewManager(ViewManager):
    close_file_title = _('Ungespeicherte Änderungen')
    close_file_txt = _('Das Dokument enthält Änderungen die <b>nicht</b> gespeichert wurden!<br><br>'
                       'Diese werden durch Schließen des Dokumentes endgültig <b>verloren</b> gehen.')
    close_file_ok = _('Schließen')
    close_clip_title = _('Zwischenablage verwerfen?')
    close_clip_txt = _('Die Zwischenablage enthält <i>{}</i> Elemente aus<br><i>{}</i><br><br>'
                       'Diese werden durch Schließen des Dokumentes aus der Zwischenablage <b>entfernt</b>.')
    close_clip_ok = _('Schließen')

    def __init__(self, ui, initial_tree_view):
        self.ui = ui
        self.app = ui.app

        super(UiViewManager, self).__init__(ui.srcTabWidget, self.app.undo_grp)

        self.filter_widget = self.ui.lineEdit_Src_filter

        self.tab.currentChanged.connect(self.ui_tab_changed)

        self.view_about_to_be_removed.connect(self.remove_view)
        self.setup_initial_tab_view(initial_tree_view)

    def setup_initial_tab_view(self, initial_tree_view):
        new_view = self.replace_tree_view(initial_tree_view)
        file = Path(_('Neues_Dokument.xml'))
        self.setup_tree_view(new_view, file=file, filter_widget=self.filter_widget)

        # Setup initial tab widget view attribute
        current_widget = self.tab.currentWidget()
        current_widget.user_view = new_view

        self.file_update.emit(file, current_widget, True)
        self.update_tab_title(self.tab.currentIndex(), file)

    def setup_default_views(self, tree_view_list: List[KnechtTreeView], tree_file_list: List[Path],
                            tree_filter_widgets: List[QLineEdit]):
        """ initial tree view setup on application start """
        new_views = list()
        for idx, (tree_view, file, filter_widget) in enumerate(zip(
                tree_view_list, tree_file_list, tree_filter_widgets)):
            new_view = self.replace_tree_view(tree_view)
            new_views.append(new_view)
            self.setup_tree_view(new_view, file=Path(file), filter_widget=filter_widget)

        # Reset focus to default tab.
        # Done once on application start to avoid menus
        # accessing already deleted views.
        self.current_view().setFocus(Qt.OtherFocusReason)

        # Return replaced tree views
        return new_views

    @Slot(int)
    def ui_tab_changed(self, index):
        """ View Manager Tab changed signal """
        current_tab = self.tab.widget(index)
        if hasattr(current_tab, 'none_document_tab'):
            return

        current_view = current_tab.user_view
        self.ui.set_last_focus_tree(current_view)
        self.ui.pushButton_Dest_show.toggled.emit(self.ui.pushButton_Dest_show.isChecked())

    def tab_view_saved(self, file: Path):
        """
            Document inside tab widget was saved, set TreeView undostack clean
            and update file_mgr if necessary
        """
        current_view = self.current_view()
        current_widget = self.tab.currentWidget()

        # Update File Manager
        if file != self.file_mgr.get_file_from_widget(current_widget):
            LOGGER.debug('Updating File Manager with changed widget+file pair.')
            self.widget_about_to_be_removed.emit(current_widget)
            self.file_update.emit(file, current_widget, True)
            current_view.setObjectName(file.name)

        self.update_tab_title(self.tab.currentIndex(), file)
        current_view.undo_stack.setClean()

    def additional_tree_setup(self, tree_view: KnechtTreeView):
        """ Tree Setup specific to main KnechtWindow
            called after setup_tree_view
        """
        # Connect view cleared signal
        # emitted from view when tree view model is cleared but not removed
        tree_view.view_cleared.connect(self.clear_render_presets)

        # Setup knecht UI context menu
        tree_view.context = TreeContextMenu(tree_view, self.ui)

        # Connect missing reset signal
        tree_view.reset_missing.connect(self.ui.report_missing_reset)

        # Hide ID columns
        tree_view.hideColumn(Kg.REF)
        tree_view.hideColumn(Kg.ID)

    @Slot(KnechtTreeView)
    def remove_view(self, view: KnechtTreeView):
        self.clear_render_presets(view)

        # Remove undo stack
        self.app.undo_grp.removeStack(view.undo_stack)

        # Update view focus as soon as view is actually destroyed
        view.destroyed.connect(self.tree_about_to_be_destroyed)

    @Slot(object)
    def clear_render_presets(self, view: KnechtTreeView):
        """ Clear render presets from the render tab of the provided view """
        # TODO: Clearing view with render presets in render queue results in undo unreachable
        self.ui.renderTree.editor.clear_view_render_presets(view)
        view.undo_stack.setActive(True)

    def reject_tab_remove(self):
        self.ui.msg(_('Kann Beschäftigten nicht entlassen. '
                      'Verstoß gegen Arbeitnehmerschutzgesetz festgestellt.'), 10000)
        LOGGER.info('Close of tab with busy tree view rejected.')

    def tree_about_to_be_destroyed(self, obj):
        LOGGER.debug('Tree View %s is about to be destroyed and requests another view to gain focus.', obj.objectName())

        if obj is not self.current_view():
            current_view = self.current_view()
            self.ui.set_last_focus_tree(current_view)
            LOGGER.debug('Successfully set %s as new focus view.', current_view.objectName())
        else:
            LOGGER.critical('Could not focus a view that is not about to be destroyed. Panic!!!')
            LOGGER.critical('Any follow up calls to menu actions will crash PySide2.')
            raise RuntimeError(f'{repr(self)} in {self.__module__} is about to access an destroyed C++ object.')

    def ask_on_close(self, tab_view) -> bool:
        """ Ask the user if he really wants to clear all items from Clipboard due to document close.

        :returns bool: False - Abort Close; True - Continue Close
        """
        # Ask on unsaved changes
        if not tab_view.undo_stack.isClean():
            msg_box = AskToContinue(self.ui)
            self.ui.play_hint_sound()

            if not msg_box.ask(self.close_file_title, self.close_file_txt, self.close_file_ok):
                # User wants to abort close action
                return False

        # Ask to continue - clear clipboard
        if self.ui.clipboard.origin is not tab_view:
            return True

        msg_box = AskToContinue(self.ui)
        self.ui.play_hint_sound()

        if not msg_box.ask(self.close_clip_title,
                           self.close_clip_txt.format(len(self.ui.clipboard.items), tab_view.objectName()),
                           self.close_clip_ok):
            # User wants to abort close action
            return False

        self.ui.clipboard.clear()

        return True
