from typing import Any, Union

from PySide2.QtGui import QIcon
from PySide2.QtWidgets import QPushButton, QTreeView, QWizard, QWizardPage

from modules.globals import Resource
from modules.gui.gui_utils import SetupWidget, replace_widget
from modules.gui.ui_resource import IconRsc
from modules.idgen import create_uuid
from modules.itemview.data_read import KnechtDataToModel
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


class PresetWizardPage(QWizardPage):

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

        self.trim = [x for x in wizard.session.data.import_data.models if x.model == model][0]

        self.setTitle(f'Preset - {self.trim.model_text}')
        self.setSubTitle(f'{model}_{fakom}')

        SetupWidget.from_ui_file(self, Resource.ui_paths['wizard_preset'])

        # -- Setup Page Ui --
        self.option_auto_btn: QPushButton
        self.option_auto_btn.setText(_('Preset auto&magisch befüllen'))
        self.option_auto_btn.setIcon(IconRsc.get_icon('qub_button'))
        self.option_auto_btn.setStatusTip(_('Aktuelles Preset automagisch mit nicht verwendeten Optionen befüllen. '
                                            'Bezugs-, Sitz-, Leder oder Fahrwerksoptionen werden ignoriert.'))

        self.option_hide_btn: QPushButton
        eye_icon = IconRsc.get_icon('eye')
        eye_icon.addPixmap(IconRsc.get_pixmap('eye-disabled'), QIcon.Normal, QIcon.On)
        self.option_hide_btn.setIcon(eye_icon)
        self.option_hide_btn.setStatusTip(_('Bereits verwendete Optionen ein- oder ausblenden'))

        self.option_lock_btn: QPushButton
        lock_icon = IconRsc.get_icon('lock_open')
        lock_icon.addPixmap(IconRsc.get_pixmap('lock'), QIcon.Normal, QIcon.On)
        self.option_lock_btn.setIcon(lock_icon)
        self.option_lock_btn.setStatusTip(_('Bereits verwendete Optionen für die Bearbeitung sperren'))
        self.option_lock_btn.toggled.connect(self.update_available_options)

        # -- Replace Placeholder TreeViews --
        self.pkg_tree = self._init_tree_view(self.pkg_tree, self.wizard.session.pkg_models.get(model))
        self.option_tree = self._init_tree_view(self.option_tree, self.wizard.session.opt_models.get(model))

        # -- Setup Preset Tree --
        self.preset_tree = self._init_tree_view(self.preset_tree, KnechtModel())
        self.preset_tree.supports_drop = True
        self.preset_tree.is_render_view = True
        self.preset_tree.view_refreshed.connect(self.update_available_options)

    def _init_tree_view(self, tree_view: QTreeView, item_model: KnechtModel) -> KnechtTreeView:
        """ Replace the UI Designer placeholder tree views """
        parent = tree_view.parent()
        new_view = KnechtTreeView(parent, None)
        replace_widget(tree_view, new_view)

        # Preset wizard specific
        new_view.setEditTriggers(QTreeView.NoEditTriggers)
        new_view.supports_drag_move = False
        new_view.supports_drop = False

        # Setup filter widget
        new_view.filter_text_widget = self.line_edit_preset
        # Setup keyboard shortcuts
        new_view.shortcuts = KnechtTreeViewShortcuts(new_view)
        # new_view.context =

        # Update with placeholder Model to avoid access to unset attributes
        UpdateModel(new_view).update(item_model or KnechtModel())

        for column in (Kg.VALUE, Kg.TYPE, Kg.REF, Kg.ID):
            new_view.hideColumn(column)

        return new_view

    def load_model(self, item_model: KnechtModel):
        UpdateModel(self.preset_tree).update(item_model)
        self.preset_tree.refresh()

    def update_available_options(self):
        """ Update PR-Options and Packages Trees based on Preset Tree Content """
        used_pr_families = self._collect_tree_pr_families(self.preset_tree)
        self.wizard.session.update_available_options(used_pr_families, self)

    @staticmethod
    def _collect_tree_pr_families(view: KnechtTreeView):
        pr_families = set()

        for index, item in view.editor.iterator.iterate_view():
            variant_ls = view.editor.collect.collect_index(index)

            for variant in variant_ls.variants:
                pr_families.add(variant.item_type)

        return pr_families

    def initializePage(self):
        pass

    def validatePage(self):
        """ Set wizard data upon page exit """
        return True
