from pathlib import Path
from queue import Queue, Empty
from typing import Optional
from threading import Thread

from PySide2.QtCore import QTimer, QUrl
from PySide2.QtGui import QDesktopServices
from PySide2.QtWidgets import QWidget, QLineEdit, QHeaderView, QLabel, QPushButton
from plmxml import PlmXml, NodeInfo
from plmxml.configurator import PlmXmlBaseConfigurator

from modules.globals import Resource
from modules.gui.gui_utils import SetupWidget, replace_widget
from modules.gui.widgets.path_util import path_exists
from modules.itemview.item import KnechtItem, KnechtItemStyle
from modules.itemview.model import KnechtModel
from modules.itemview.model_update import UpdateModel
from modules.itemview.tree_view import KnechtTreeView
from modules.itemview.tree_view_utils import KnechtTreeViewShortcuts
from modules.knecht_objects import KnechtVariantList
from modules.knecht_plmxml import create_pr_string_from_variants
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class KnechtPlmXmlScene(QWidget):

    def __init__(self, ui, plmxml_file: Path, variants: KnechtVariantList):
        """ Generic welcome page

        :param modules.gui.main_ui.KnechtWindow ui: Knecht main window
        """
        super(KnechtPlmXmlScene, self).__init__(ui)
        SetupWidget.from_ui_file(self, Resource.ui_paths['knecht_plmxml_scene'])
        self.ui = ui
        self.setWindowTitle(_('PlmXml Schnuffi'))
        self.plmxml: Optional[PlmXml] = None

        # -- Prepare UI
        self.searchScene: QLineEdit = self.searchScene
        self.searchMaterials: QLineEdit = self.searchMaterials

        # -- File name label
        self.fileLabel: QLabel = self.fileLabel
        self.fileLabel.setText(plmxml_file.name)

        # -- Config Label
        self.configLabel: QLabel = self.configLabel
        self.configLabel.setText(variants.preset_name)

        # -- Config Button
        self.configBtn: QPushButton = self.configBtn
        self.configBtn.toggled.connect(self.toggle_config)
        if not len(variants):
            self.configBtn.setEnabled(False)

        self.config = PlmXmlBaseConfigurator(None, create_pr_string_from_variants(variants))

        # -- Open file dir button
        self.fileButton: QPushButton = self.fileButton
        self.fileButton.pressed.connect(self.open_desktop_directory)

        # -- Prepare PlmXml Scene View
        self.scene_tree = KnechtTreeView(self, None)
        self.scene_tree.filter_text_widget = self.searchScene
        self.scene_tree.setIndentation(18)
        # Setup keyboard shortcuts
        shortcuts = KnechtTreeViewShortcuts(self.scene_tree)
        self.scene_tree.shortcuts = shortcuts

        # -- Prepare PlmXml Material View
        self.material_tree = KnechtTreeView(self, None)
        self.material_tree.filter_text_widget = self.searchMaterials
        # Setup keyboard shortcuts
        shortcuts = KnechtTreeViewShortcuts(self.material_tree)
        self.material_tree.shortcuts = shortcuts

        # -- Replace Trees
        replace_widget(self.sceneTree, self.scene_tree)
        replace_widget(self.materialTree, self.material_tree)

        # -- Delete UI Template Trees
        self.sceneTree.deleteLater()
        self.materialTree.deleteLater()

        # -- Workaround PySide2 bug
        self.scene_tree.show()
        self.material_tree.show()

        self.q = Queue()
        t = Thread(target=self.read_plmxml, args=(plmxml_file, self.q))
        t.start()
        self.timer = QTimer()
        self.timer.setSingleShot(False)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.check_q)
        self.timer.start()

    @staticmethod
    def read_plmxml(plmxml_file: Path, q: Queue):
        plmxml = PlmXml(plmxml_file, read_tree_hierarchy=True)
        q.put(plmxml)

    def check_q(self):
        try:
            result = self.q.get_nowait()
            self.plmxml = result
            self.config.plmxml = self.plmxml
            self.timer.stop()
            self.build_data_trees()
        except Empty:
            pass

    def open_desktop_directory(self):
        """ Open directory with desktop explorer """
        if path_exists(self.plmxml.file.parent):
            q = QUrl.fromLocalFile(self.plmxml.file.parent.as_posix())
            QDesktopServices.openUrl(q)

    def _enable_config_btn(self):
        self.configBtn.setEnabled(True)

    def toggle_config(self, checked):
        self.configBtn.setEnabled(False)
        QTimer.singleShot(5000, self._enable_config_btn)
        self.build_data_trees(checked)

    def build_data_trees(self, use_config: bool = False):
        if use_config:
            LOGGER.debug('Updating PlmXml configuration')
            self.config.update()

        self._build_scene_tree(use_config)
        self._build_material_tree(use_config)
        QTimer.singleShot(2000, self.setup_header)

    def _build_material_tree(self, use_config: bool = False):
        material_root_item = KnechtItem(data=('', 'Material Name', 'PR-Tags', 'Desc'))

        for idx, (name, target) in enumerate(self.plmxml.look_lib.materials.items()):
            child_idx = material_root_item.childCount()

            material_root_item.insertChildren(
                child_idx, 1, (f'{idx:03d}', name, '', '')
            )
            target_item = material_root_item.child(child_idx)
            KnechtItemStyle.style_column(target_item, 'fakom_option')

            # -- Create Material Variants
            for c_idx, v in enumerate(target.variants):
                # -- Skip invisible variants in Config Display
                if use_config:
                    if v != target.visible_variant:
                        continue
                target_child_idx = target_item.childCount()
                target_item.insertChildren(
                    target_child_idx, 1, (f'{c_idx:03d}', v.name, v.pr_tags, v.desc)
                )
                if use_config:
                    variant_item = target_item.child(target_child_idx)
                    variant_item.style_bg_green()

        update_material_tree = UpdateModel(self.material_tree)
        update_material_tree.update(KnechtModel(material_root_item))

    def _iterate_scene_children(self, idx: int, node: NodeInfo, parent_item: KnechtItem, use_config: bool = False):
        child_idx = parent_item.childCount()
        parent_item.insertChildren(child_idx, 1, (f'{idx:03d}', node.name, node.pr_tags, node.trigger_rules))
        node_item = parent_item.child(child_idx)

        # -- Style Schaltgruppen
        if node.pr_tags:
            KnechtItemStyle.style_column(node_item, 'plmxml_item')

        # -- Style visible nodes in Config Display
        if use_config and node.visible:
            node_item.style_bg_green()

        # -- Skip invisible child nodes in Config Display
        if use_config and node.pr_tags and not node.visible:
            node_item.style_recursive()
            return

        for idx, child_node in enumerate(self.plmxml.iterate_child_nodes(node)):
            self._iterate_scene_children(idx, child_node, node_item, use_config)

    def _build_scene_tree(self, use_config: bool):
        scene_root_item = KnechtItem(data=('', 'Name', 'PR-Tags', 'Trigger Rules'))

        for idx, node in enumerate(self.plmxml.iterate_root_nodes()):
            self._iterate_scene_children(idx, node, scene_root_item, use_config)

        update_scene_tree = UpdateModel(self.scene_tree)
        update_scene_tree.update(KnechtModel(scene_root_item))

    def setup_header(self):
        for widget in (self.scene_tree, self.material_tree):
            header = widget.header()
            header.hideSection(4)
            header.hideSection(5)
            header.hideSection(6)
            header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
            header.setStretchLastSection(True)
