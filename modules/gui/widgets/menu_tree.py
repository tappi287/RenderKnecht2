from PySide2.QtCore import Slot
from PySide2.QtWidgets import QMenu, QAction, QActionGroup, QMainWindow

from modules.gui.ui_resource import IconRsc
from modules.gui.widgets.message_box import AskToContinue
from modules.itemview.tree_view import KnechtTreeView
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class TreeMenu(QMenu):
    def __init__(self, parent_widget, ui, menu_name: str=_('Baum')):
        """
        :param modules.gui.main_ui.KnechtWindow ui: The main ui class
        :param str menu_name: Edit Menu display name
        """
        super(TreeMenu, self).__init__(menu_name, parent_widget)

        self.parent_widget = parent_widget
        self.ui = ui
        self.view: KnechtTreeView = None

        sort_view = QAction(IconRsc.get_icon('sort'), _('Breite der Kopfspalten an Bauminhalt anpassen'), self)
        sort_view.triggered.connect(self.sort_current_tree)
        quick_view = QAction(IconRsc.get_icon('eye'), _('Schnellansicht ein-/ausschalten'), self)
        quick_view.triggered.connect(self.ui.pushButton_Dest_show.animateClick)
        self.clear_view = QAction(IconRsc.get_icon('delete_list'), _('Bauminhalt vollständig verwerfen'), self)
        self.clear_view.triggered.connect(self.clear_current_tree)
        self.addActions([sort_view, quick_view, self.clear_view])

        self.addSeparator()

        reset_filter = QAction(IconRsc.get_icon('reset'), _('Filter zurücksetzen\tEsc'), self)
        reset_filter.triggered.connect(self.clear_view_filter)
        collapse_all = QAction(IconRsc.get_icon('options'), _('Bauminhalte vollständig einklappen\t2x Esc'), self)
        collapse_all.triggered.connect(self.collapse_tree)
        self.addActions([reset_filter, collapse_all])

        self.addSeparator()

        self.move_grp = QActionGroup(self)
        self.m_up = QAction(IconRsc.get_icon('arrow_up'),
                            _('Selektierte Elemente aufwärts verschieben\tPfeil auf'),
                            self.move_grp)
        self.m_dn = QAction(IconRsc.get_icon('arrow'),
                            _('Selektierte Elemente abwärts verschieben\tPfeil ab'),
                            self.move_grp)
        self.j_up = QAction(IconRsc.get_icon('arrow_up'),
                            _('Selektierte Elemente 10 Schritte aufwärts verschieben\tBild auf'),
                            self.move_grp)
        self.j_dn = QAction(IconRsc.get_icon('arrow'),
                            _('Selektierte Elemente 10 Schritte abwärts verschieben\tBild ab'),
                            self.move_grp)
        self.move_grp.triggered.connect(self.move)
        self.addActions([self.m_up, self.m_dn, self.j_up, self.j_dn])

        self.aboutToShow.connect(self.update_current_view)

    def move(self, action: QAction):
        if not self.view.supports_drag_move:
            return

        if action is self.m_up:
            self.view.editor.move_rows_keyboard(move_up=True)
        elif action == self.m_dn:
            self.view.editor.move_rows_keyboard(move_up=False)
        elif action == self.j_up:
            self.view.editor.move_rows_keyboard(move_up=True, jump=True)
        elif action == self.j_dn:
            self.view.editor.move_rows_keyboard(move_up=False, jump=True)

    def sort_current_tree(self):
        if self.view is self.ui.variantTree:
            self.ui.variantTree.sort_tree()
        elif self.view is self.ui.renderTree:
            self.ui.renderTree.sort_tree()
        else:
            self.view.sort_tree()

    def clear_view_filter(self):
        self.view.clear_filter()

    def collapse_tree(self):
        self.view.collapseAll()

    def clear_current_tree(self):
        if not self._ask_clear():
            return
        self.view.clear_tree()

    def _ask_clear(self):
        msg_box = AskToContinue(self)

        if not msg_box.ask(
            title=_('Bauminhalt verwerfen'),
            txt=_('Soll der Bauminhalt von<br/><i>{}</i><br/>wirklich vollständig <b>verworfen</b> werden?'
                  ).format(self.view.objectName()),
            ok_btn_txt=_('Ja'),
            abort_btn_txt=_('Nein'),
                ):
            return False

        return True

    @Slot()
    def update_current_view(self):
        current_view = None

        if isinstance(self.parent_widget, QMainWindow):
            current_view = self.parent_widget.view_mgr.current_view()
            LOGGER.debug('Tree Menu about to show from Main Window Menu.')
        elif isinstance(self.parent_widget, QMenu):
            current_view = self.parent_widget.view
            LOGGER.debug('Tree Menu about to show from Context Menu.')

        self.view = current_view

        self.clear_view.setText(_('{} vollständig verwerfen').format(self.view.objectName()[:38]))
