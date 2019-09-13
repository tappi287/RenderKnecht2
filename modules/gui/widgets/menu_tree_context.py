from pathlib import Path

from PySide2 import QtCore
from PySide2.QtCore import QUrl
from PySide2.QtGui import QDesktopServices, QKeySequence
from PySide2.QtWidgets import QAction, QActionGroup, QMenu, QPushButton

from modules.globals import get_settings_dir
from modules.gui.ui_resource import IconRsc
from modules.gui.widgets.menu_create import CreateMenu
from modules.gui.widgets.menu_tree import TreeMenu
from modules.gui.widgets.path_util import path_exists
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.knecht_update import restart_knecht_app
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class TreeContextMenu(QMenu):
    def __init__(self, view, ui, menu_name: str = _('Baum Kontextmenü')):
        """ Context menu of tree views

        :param modules.itemview.tree_view.KnechtTreeView view: tree view
        :param KnechtWindow ui: main window ui class
        :param str menu_name: name of the menu
        """
        super(TreeContextMenu, self).__init__(menu_name, view)
        self.view, self.ui, self.status_bar = view, ui, ui.statusBar()

        self.edit_menu = self.ui.main_menu.edit_menu
        self.create_menu = CreateMenu(self)
        self.tree_menu = TreeMenu(self, ui)

        self.send_dg_action = QAction(IconRsc.get_icon('paperplane'), _('Senden an DeltaGen'), self)
        dg_tip_1 = _('Selektierte Bauminhalte als Variantenschaltung mit vorherigem Reset an DeltaGen senden.')
        self.send_dg_action.setToolTip(dg_tip_1)
        self.send_dg_action.setStatusTip(dg_tip_1)
        self.send_dg_action.triggered.connect(self.send_to_deltagen)
        self.addAction(self.send_dg_action)
        self.addSeparator()

        self.send_dg_short = QAction(IconRsc.get_icon('paperplane'), _('Ohne Reset an DeltaGen senden'), self)
        dg_tip_2 = _('Selektierte Bauminhalte ohne einen Reset an DeltaGen senden.')
        self.send_dg_short.setToolTip(dg_tip_2)
        self.send_dg_short.setStatusTip(dg_tip_2)
        self.send_dg_short.triggered.connect(self.send_to_deltagen_wo_reset)
        self.addAction(self.send_dg_short)
        self.addSeparator()

        copy_pr = QAction(IconRsc.get_icon('options'), _('PR String in Zwischenablage kopieren'), self)
        copy_pr.triggered.connect(self.copy_strings_to_clipboard)
        self.addAction(copy_pr)
        self.addSeparator()

        # ---- Create preset from selected actions ----
        self.addActions([
            self.create_menu.user_preset_from_selected,
            self.create_menu.render_preset_from_selected
            ])
        self.addSeparator()

        # ---- Prepare Context Menus & Actions ----
        # ---- Add main menu > edit -----
        self.addMenu(self.edit_menu)
        # ---- Add main menu > tree -----
        self.addMenu(self.tree_menu)
        # ---- Add main menu > create -----
        self.addMenu(self.create_menu)

        self.addSeparator()

        self.remove_row_action = QAction(IconRsc.get_icon('trash-a'), _('Selektierte Zeilen entfernen\tEntf'), self)
        self.remove_row_action.triggered.connect(self.edit_menu.remove_rows_action.trigger)
        self.addAction(self.remove_row_action)

        self.addSeparator()

        # ---- Developer Actions -----
        self.dev_actions = QActionGroup(self)
        cake = QAction(IconRsc.get_icon('layer'), '--- The cake was a lie ---', self.dev_actions)

        show_id_action = QAction(IconRsc.get_icon('options'), 'Show ID columns', self.dev_actions)
        show_id_action.triggered.connect(self.show_id_columns)

        hide_id_action = QAction(IconRsc.get_icon('options-neg'), _('Hide ID columns'), self.dev_actions)
        hide_id_action.triggered.connect(self.hide_id_columns)

        list_tab_widgets = QAction(IconRsc.get_icon('navicon'), 'List Tab Widgets', self.dev_actions)
        list_tab_widgets.triggered.connect(self.list_tab_widgets)

        report_action = QAction('Report Item attributes to log', self.dev_actions)
        report_action.setShortcut(QKeySequence('Ctrl+B'))
        report_action.triggered.connect(self.report_current)

        log_level = QAction(IconRsc.get_icon('sort'), 'Enable DEBUG log level', self.dev_actions)
        log_level.triggered.connect(self.ui.app.set_debug_log_level)

        produce_exception = QAction(IconRsc.get_icon('warn'), 'Produce Exception', self.dev_actions)
        produce_exception.triggered.connect(self.ui.app.produce_exception)

        open_dir = QAction(IconRsc.get_icon('folder'), 'Open Settings Directoy', self.dev_actions)
        open_dir.triggered.connect(self.open_settings_dir)

        notify = QAction(IconRsc.get_icon('eye-disabled'), 'Show tray notification', self.dev_actions)
        notify.triggered.connect(self.noclick_tray_notification)

        notify_click = QAction(IconRsc.get_icon('eye'), 'Show click tray notification', self.dev_actions)
        notify_click.triggered.connect(self.click_tray_notification)

        overlay_btn_msg = QAction(IconRsc.get_icon('check_box'), 'Show overlay confirm message', self.dev_actions)
        overlay_btn_msg.triggered.connect(self.overlay_confirm_message)

        overlay_msg = QAction(IconRsc.get_icon('check_box_empty'), 'Show regular overlay message', self.dev_actions)
        overlay_msg.triggered.connect(self.overlay_message)

        overlay_imm_msg = QAction(IconRsc.get_icon('reset'), 'Show immediate overlay message', self.dev_actions)
        overlay_imm_msg.triggered.connect(self.overlay_message_immediate)

        restart = QAction(IconRsc.get_icon('reset'), 'Restart', self.dev_actions)
        restart.triggered.connect(self.restart_app)

        reorder = QAction(IconRsc.get_icon('sort'), 'Rewrite item order whole tree', self.dev_actions)
        reorder.triggered.connect(self.reorder_tree)

        self.addActions(self.dev_actions.actions())
        self.dev_actions.setVisible(False)

        self.aboutToShow.connect(self.update_actions)

        # TODO: Add Actions expand all, collapse all, clear filter

        # Install context menu event filter
        self.view.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is not self.view:
            return False

        if event.type() == QtCore.QEvent.ContextMenu:
            self.dev_actions.setVisible(False)

            # Hold Control and Shift to display dev context
            if event.modifiers() == QtCore.Qt.ShiftModifier | QtCore.Qt.ControlModifier:
                self.dev_actions.setVisible(True)

            self.popup(event.globalPos())
            return True

        return False

    def send_to_deltagen(self):
        variants = self.view.editor.collect.collect_current_index()
        self.ui.app.send_dg.send_variants(variants, self.view)

    def send_to_deltagen_wo_reset(self):
        variants = self.view.editor.collect.collect_current_index(collect_reset=False)
        self.ui.app.send_dg.send_variants(variants, self.view)

    def copy_strings_to_clipboard(self):
        variants = self.view.editor.collect.collect_current_index(collect_reset=False)

        pr_string = ''
        for variant in variants.variants:
            pr_string += f'{variant.name} {variant.value};'

        self.ui.app.clipboard().setText(pr_string)

    def hide_id_columns(self):
        self.view.hideColumn(Kg.REF)
        self.view.hideColumn(Kg.ID)

    def show_id_columns(self):
        self.view.showColumn(Kg.REF)
        self.view.showColumn(Kg.ID)

    def list_tab_widgets(self):
        self.ui.view_mgr.log_tabs()

    def report_current(self):
        self.view.editor.report_current()

    def open_settings_dir(self):
        settings_dir = Path(get_settings_dir())

        if path_exists(settings_dir):
            q = QUrl.fromLocalFile(settings_dir.as_posix())
            QDesktopServices.openUrl(q)

    def noclick_tray_notification(self):
        self.ui.show_tray_notification(
            title='Test Notification',
            message='Clicking the message should hopefully emit nothing.'
            )

    def click_tray_notification(self):
        def test_callback():
            LOGGER.info('Test notification click callback activated.')
            self.ui.msg('Message triggered by notification messageClicked.', 4000)

        self.ui.show_tray_notification(
            title='Test Notification',
            message='Clicking the message should trigger a overlay message.',
            clicked_callback=test_callback
            )

    def restart_app(self):
        restart_knecht_app(self.ui)

    def reorder_tree(self):
        for idx, _ in self.view.editor.iterator.iterate_view():
            self.view.editor.iterator.order_items(idx)

    def overlay_message(self):
        self.view.info_overlay.display('Message in queue for a duration of 5000ms', 5000)

    def overlay_message_immediate(self):
        self.view.info_overlay.display('Immediate message for a duration of 6000ms', 6000, True)

    def overlay_confirm_message(self):
        buttons = (('Buttontext 1', None), ('Buttontext 2', None))
        self.view.info_overlay.display_confirm('Test Message to confirm something. '
                                               'Lenghty information ahead! This message ends '
                                               'with this sentence.', buttons)

    def update_actions(self):
        src_model = self.view.model().sourceModel()
        if src_model.id_mgr.has_recursive_items():
            self.send_dg_action.setEnabled(False)
            self.send_dg_short.setEnabled(False)
        else:
            self.send_dg_action.setEnabled(True)
            self.send_dg_short.setEnabled(True)

        self.create_menu.update_current_view()

        if self.view.is_render_view:
            self.send_dg_action.setEnabled(False)
            self.send_dg_short.setEnabled(False)
