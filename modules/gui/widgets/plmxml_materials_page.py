from PySide2.QtCore import Qt
from PySide2.QtWidgets import QWidget, QTreeWidget, QTreeWidgetItem

from modules.globals import Resource
from modules.gui.gui_utils import SetupWidget
from modules.language import get_translation
from modules.log import init_logging
from plmxml import PlmXml

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class KnechtPlmXmlMaterialsPage(QWidget):

    def __init__(self, ui, plmxml: PlmXml):
        """ List plmxml materials

        :param modules.gui.main_ui.KnechtWindow ui: Knecht main window
        """
        super(KnechtPlmXmlMaterialsPage, self).__init__()
        SetupWidget.from_ui_file(self, Resource.ui_paths['knecht_plmxml_materials'])
        self.ui = ui
        self.setWindowTitle(_('PlmXml Materialien'))
        self.treeWidget: QTreeWidget

        self.plmxml = plmxml

        self.headline_label.setText(plmxml.file.name + _(' Quell Materialien'))
        self.update_page()

    def update_page(self):
        look_variants = dict()

        for l in self.plmxml.look_lib.materials.values():
            for variant in l.variants:
                look_variants[variant.name] = variant.desc

        # Add items
        for name, desc in look_variants.items():
            item = QTreeWidgetItem(self.treeWidget, [name, desc])
            item.setFlags(item.flags() | Qt.ItemIsEditable)
