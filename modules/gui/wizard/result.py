import time

from PySide2.QtCore import QTimer
from PySide2.QtWidgets import QTreeView, QWizardPage

from modules.globals import Resource
from modules.gui.gui_utils import SetupWidget, replace_widget
from modules.gui.ui_resource import IconRsc
from modules.itemview.model import KnechtModel
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.itemview.model_update import UpdateModel
from modules.itemview.tree_view import KnechtTreeView
from modules.itemview.tree_view_utils import KnechtTreeViewShortcuts
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class ResultWizardPage(QWizardPage):
    def __init__(self, wizard):
        """ Wizard Result Page

        :param modules.gui.wizard.wizard.PresetWizard wizard: The parent wizard
        """
        super(ResultWizardPage, self).__init__()
        self.wizard = wizard
        SetupWidget.from_ui_file(self, Resource.ui_paths['wizard_result'])

        self.setTitle(_('Wizard Ergebnis'))
        self.setSubTitle(_('Überblick über nicht verwendete Optionen und Pakete'))

        # --- Tree Views ---
        self.result_tree = self._init_tree_view(self.result_tree)

    def initializePage(self):
        self.collect_unused_options()
        LOGGER.info('Result Wizard Page initialized.')

    def cleanupPage(self):
        self.result_tree.clear_tree()

    def collect_unused_options(self):
        # Add Unused Packages
        pkg_items = self._collect_unused_from_modeldict(self.wizard.session.pkg_models)
        self.result_tree.editor.create_top_level_rows(pkg_items, at_row=0)

        self.result_tree.block_until_editor_finished()

        # Add Unused PR-Options
        pr_items = self._collect_unused_from_modeldict(self.wizard.session.opt_models)
        self.result_tree.editor.create_top_level_rows(pr_items)

    def _init_tree_view(self, tree_view: QTreeView) -> KnechtTreeView:
        """ Replace the UI Designer placeholder tree views """
        parent = tree_view.parent()
        new_view = KnechtTreeView(parent, None)
        replace_widget(tree_view, new_view)

        # Result wizard specific
        # new_view.setEditTriggers(QTreeView.NoEditTriggers)
        new_view.setDragDropMode(QTreeView.NoDragDrop)
        new_view.supports_drag_move = False
        new_view.supports_drop = False

        # Setup filter widget
        new_view.filter_text_widget = self.filter_edit
        # Setup keyboard shortcuts
        new_view.shortcuts = KnechtTreeViewShortcuts(new_view)

        # Update with placeholder Model to avoid access to unset attributes
        UpdateModel(new_view).update(KnechtModel())

        for column in (Kg.VALUE, Kg.TYPE, Kg.REF, Kg.ID):
            new_view.hideColumn(column)

        return new_view

    def validatePage(self):
        return True

    @staticmethod
    def _collect_unused_from_modeldict(model_dict):
        unused_options = list()

        for model_code, item_model in model_dict.items():
            for item in item_model.root_item.iter_children():
                if not item.fixed_userType:  # Option is unlocked
                    unused_options.append(item.copy())

        LOGGER.debug('Collected %s unused options.', len(unused_options))
        return unused_options
