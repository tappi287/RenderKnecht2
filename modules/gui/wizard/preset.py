from PySide2.QtCore import QTimer, Qt, QEvent, QObject
from PySide2.QtGui import QIcon, QKeySequence
from PySide2.QtWidgets import QPushButton, QTreeView, QWizardPage, QWizard, QLineEdit, QMenu, QAction

from modules.globals import Resource
from modules.gui.gui_utils import SetupWidget, replace_widget
from modules.gui.ui_resource import IconRsc
from modules.itemview.model import KnechtModel
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.itemview.model_update import UpdateModel
from modules.itemview.tree_view import KnechtTreeView
from modules.itemview.tree_view_utils import KnechtTreeViewShortcuts
from modules.knecht_objects import KnTrim
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class PresetWizardPage(QWizardPage):
    hidden_columns_a = (Kg.VALUE, Kg.TYPE, Kg.REF, Kg.ID)
    hidden_columns_b = (Kg.DESC, Kg.VALUE, Kg.TYPE, Kg.REF, Kg.ID)

    # Automagic Defaults
    automagic_pr_num = 13
    automagic_pkg_num = 3

    def __init__(self, wizard, model: str, fakom: str):
        """ Page for one Preset with available PR-Options and Packages tree's

        :param modules.gui.wizard.wizard.PresetWizard wizard: The parent wizard
        :param str model: model code
        :param str fakom: fakom code
        """
        super(PresetWizardPage, self).__init__()
        self.wizard = wizard
        self.model = model
        self.fakom = fakom

        trim = [x for x in wizard.session.data.import_data.models if x.model == model][0]
        SetupWidget.from_ui_file(self, Resource.ui_paths['wizard_preset'])

        # -- Title --
        num = 1 + len(self.wizard.session.data.preset_page_ids)
        self.setTitle(f'{num:02d}/{self.wizard.session.data.preset_page_num:02d} Preset - {trim.model_text}')

        # -- Sub Title Update Timer --
        self.update_title_timer = QTimer()
        self.update_title_timer.setInterval(25)
        self.update_title_timer.setSingleShot(True)
        self.update_title_timer.timeout.connect(self.update_page_title)

        # -- Trigger filter update for all views ---
        self.update_filter_timer = QTimer()
        self.update_filter_timer.setInterval(5)
        self.update_filter_timer.setSingleShot(True)
        self.update_filter_timer.timeout.connect(self.update_filter_all_views)

        self.line_edit_preset: QLineEdit
        self.line_edit_preset.textChanged.connect(self.update_filter_timer.start)

        # -- Setup Page Ui --
        self.option_auto_btn: QPushButton
        self.option_auto_btn.setText(_('Preset auto&magisch befüllen'))
        self.option_auto_btn.setIcon(IconRsc.get_icon('qub_button'))
        self.option_auto_btn.setStatusTip(_('Aktuelles Preset automagisch mit nicht verwendeten Optionen befüllen. '
                                            'Bezugs-, Sitz-, Leder oder Fahrwerksoptionen werden ignoriert.'))
        self.option_auto_btn.released.connect(self.fill_automagically)

        self.option_hide_btn: QPushButton
        eye_icon = IconRsc.get_icon('eye')
        eye_icon.addPixmap(IconRsc.get_pixmap('eye-disabled'), QIcon.Normal, QIcon.On)
        self.option_hide_btn.setIcon(eye_icon)
        self.option_hide_btn.setStatusTip(_('Bereits verwendete Optionen ein- oder ausblenden'))
        self.option_hide_btn.toggled.connect(self.update_available_options)

        self.option_lock_btn: QPushButton
        lock_icon = IconRsc.get_icon('lock_open')
        lock_icon.addPixmap(IconRsc.get_pixmap('lock'), QIcon.Normal, QIcon.On)
        self.option_lock_btn.setIcon(lock_icon)
        self.option_lock_btn.setStatusTip(_('Bereits verwendete Optionen für die Bearbeitung sperren'))
        self.option_lock_btn.toggled.connect(self.update_available_options)

        self.option_tree_btn: QPushButton
        opt_icon = QIcon(IconRsc.get_pixmap('options'))
        opt_icon.addPixmap(IconRsc.get_pixmap('options-neg'), QIcon.Normal, QIcon.On)
        self.option_tree_btn.setIcon(opt_icon)
        self.option_tree_btn.setStatusTip(_('Spalte Beschreibung ein- oder ausblenden'))
        self.option_tree_btn.toggled.connect(self.update_view_headers)

        # -- Replace Placeholder TreeViews --
        self.pkg_tree = self._init_tree_view(self.pkg_tree, self.wizard.session.pkg_models.get(model))
        self.pkg_tree.permanent_type_filter_column = Kg.VALUE
        self.option_tree = self._init_tree_view(self.option_tree, self.wizard.session.opt_models.get(model))
        self.option_tree.permanent_type_filter_column = Kg.NAME

        # -- Setup Preset Tree --
        self.preset_tree = self._init_tree_view(self.preset_tree, KnechtModel())
        self.preset_tree.supports_drop = True
        self.preset_tree.supports_drag_move = True
        self.preset_tree.is_render_view = True
        self.preset_tree.context = PresetTreeContextMenu(self.preset_tree, self.wizard)
        self.preset_tree.shortcut_override = PresetTreeViewShortcutOverrides(self.preset_tree)
        self.preset_tree.view_refreshed.connect(self.update_available_options)

        # Initial Tree sort
        QTimer.singleShot(50, self.update_view_headers)

    def remove_rows(self):
        if self.preset_tree.hasFocus():
            LOGGER.debug('Remove triggered in %s', self.title())

    def _init_tree_view(self, tree_view: QTreeView, item_model: KnechtModel) -> KnechtTreeView:
        """ Replace the UI Designer placeholder tree views """
        parent = tree_view.parent()
        new_view = KnechtTreeView(parent, self.wizard.ui.app.undo_grp)
        replace_widget(tree_view, new_view)

        # Preset wizard specific
        new_view.setEditTriggers(QTreeView.NoEditTriggers)
        new_view.supports_drag_move = False
        new_view.supports_drop = False

        # Setup filter widget
        new_view.filter_text_widget = self.line_edit_preset
        # Setup keyboard shortcuts
        new_view.shortcuts = KnechtTreeViewShortcuts(new_view)

        # Update with placeholder Model to avoid access to unset attributes
        UpdateModel(new_view).update(item_model or KnechtModel())

        for column in self.hidden_columns_a:
            new_view.hideColumn(column)

        return new_view

    def _iterate_views(self):
        for view in (self.preset_tree, self.pkg_tree, self.option_tree):
            yield view

    def update_view_headers(self):
        for view in self._iterate_views():
            for column in range(0, Kg.column_count):
                view.showColumn(column)

                if self.option_tree_btn.isChecked():
                    if column in self.hidden_columns_b:
                        view.hideColumn(column)
                else:
                    if column in self.hidden_columns_a:
                        view.hideColumn(column)

            view.sort_tree()

    def update_filter_all_views(self):
        for view in self._iterate_views():
            if not self.line_edit_preset.text():
                view.clear_filter()
            else:
                view.filter_timer.start()

    def load_model(self, item_model: KnechtModel):
        UpdateModel(self.preset_tree).update(item_model)

    def update_available_options(self):
        """ Update PR-Options and Packages Trees based on Preset Tree Content """
        self.wizard.session.update_available_options()
        self.update_title_timer.start()

    def _auto_fill_preset_tree(self, src_view: KnechtTreeView, num: int, limit: int):
        # Create PR-Options or Packages
        for _, item in src_view.editor.iterator.iterate_view():
            if num > limit:
                break

            if not item.fixed_userType:  # Option is not locked
                # Copy Package
                self.wizard.automagic_clipboard.items = [item.copy()]
                self.wizard.automagic_clipboard.origin = src_view
                # Paste Package
                self.preset_tree.editor.paste_items(self.wizard.automagic_clipboard)
                # Update available PR-Options / Packages
                self.wizard.session.update_available_options_immediately()
                self.wizard.automagic_clipboard.clear()

                num += 1

    def fill_automagically(self):
        LOGGER.debug('Automagic started on %s', self.title())
        pr_num, pkg_num = 0, 0

        # Count already existing PR-Options and Packages
        for opt_index, opt_item in self.preset_tree.editor.iterator.iterate_view():
            if opt_item.userType == Kg.variant:
                pr_num += 1
            else:
                pkg_num += 1

        # Auto fill available packages
        self._auto_fill_preset_tree(self.pkg_tree, pkg_num, self.automagic_pkg_num)
        # Auto fill available PR-Options
        self._auto_fill_preset_tree(self.option_tree, pr_num, self.automagic_pr_num)

    def update_page_title(self):
        option_names = ''
        for _, item in self.preset_tree.editor.iterator.iterate_view():
            if item.userType == Kg.variant:
                option_names += f'_{item.data(Kg.NAME)}'  # Add PR-Option to name
            else:
                option_names += f'_{item.data(Kg.VALUE)}'  # Add Package PR to name

        self.setSubTitle(f'{self.model}_{self.fakom}{option_names}')

    def setup_button_state(self):
        self.option_tree_btn.setChecked(self.wizard.session.data.column_btn)
        self.option_lock_btn.setChecked(self.wizard.session.data.lock_btn)
        self.option_hide_btn.setChecked(self.wizard.session.data.hide_btn)

    def initializePage(self):
        self.setup_button_state()
        self.update_available_options()

    def cleanupPage(self):
        """ Call initPage of previous PresetWizardPage on back button """
        self.validatePage()

        previous_page = self.wizard.page(self.wizard.currentId() - 1)
        if isinstance(previous_page, PresetWizardPage):
            previous_page.initializePage()

    def validatePage(self):
        """ Set wizard data upon page exit """
        self.wizard.session.data.lock_btn = self.option_lock_btn.isChecked()
        self.wizard.session.data.hide_btn = self.option_hide_btn.isChecked()
        self.wizard.session.data.column_btn = self.option_tree_btn.isChecked()

        return True


class PresetTreeContextMenu(QMenu):
    def __init__(self, view, wizard):
        """

        :param modules.itemview.treeview.KnechtTreeView view: the view to manipulate
        :param modules.gui.wizard.wizard.PresetWizard wizard: The parent wizard
        """
        super(PresetTreeContextMenu, self).__init__(parent=view)
        self.view = view
        self.view.installEventFilter(self)
        self.wizard = wizard

        clear = QAction(IconRsc.get_icon('delete_list'), _('Alle Optionen entfernen'), self)
        clear.triggered.connect(self.view.clear_tree)

        rem = QAction(IconRsc.get_icon('trash-a'), _('Selektierte Zeilen entfernen\tEntf'), self)
        rem.triggered.connect(self.remove_rows)

        self.addActions((clear, rem))

    def eventFilter(self, obj, event):
        if obj is not self.view:
            return False

        if event.type() == QEvent.ContextMenu:
            self.popup(event.globalPos())
            return True

        return False

    def remove_rows(self):
        if self.view.hasFocus():
            self.view.editor.remove_rows(ignore_edit_triggers=True)


class PresetTreeViewShortcutOverrides(QObject):
    def __init__(self, view):
        """ Disable Ctrl+C; Ctrl+V Shortcuts

        :param modules.itemview.tree_view.KnechtTreeView view: View to install shortcuts on
        """
        super(PresetTreeViewShortcutOverrides, self).__init__(parent=view)
        self.view = view
        self.view.installEventFilter(self)

    def eventFilter(self, obj, event):
        """ Set Knecht Tree View keyboard Shortcuts """
        if not obj or not event:
            return False

        if event.type() == QEvent.ShortcutOverride:
            # Intercept Edit Menu Shortcuts eg. Ctrl+C, Ctrl+V
            event.accept()

            if event.key() == Qt.Key_Delete:
                self.view.context.remove_rows()

            return True

        return False
