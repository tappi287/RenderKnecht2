from typing import List, Union

from PySide2.QtCore import QObject, QTimer, Slot

from modules.itemview.item import KnechtItem
from modules.itemview.model_globals import KnechtModelGlobals as Kg


class VariantInputFields(QObject):
    def __init__(self, ui):
        """ Functionality of the variant tab

        :param modules.gui.main_ui.KnechtWindow ui: main gui window
        """
        super(VariantInputFields, self).__init__(ui)
        self.ui = ui
        self.view = None
        
        # Add Variant Fields functionality
        self.ui.pushButton_addVariant.pressed.connect(self.add_variants)
        self.ui.plainTextEdit_addVariant_Setname.returnPressed.connect(self.ui.pushButton_addVariant.click)
        self.ui.plainTextEdit_addVariant_Variant.returnPressed.connect(self.ui.pushButton_addVariant.click)

        QTimer.singleShot(1, self.delayed_setup)

    @Slot()
    def delayed_setup(self):
        """ Setup attributes that require a fully initialized ui"""
        self.view = self.ui.variantTree

    def add_variants(self):
        # Get text from Variant Set field
        variant_set_str = self.ui.plainTextEdit_addVariant_Setname.text()

        # Get text from Variant field
        variant_str = self.ui.plainTextEdit_addVariant_Variant.text()

        # Set to placeholder text if left empty
        if variant_str == '':
            variant_str = self.ui.plainTextEdit_addVariant_Variant.placeholderText()

        # Text contains semicolons, guess as old RenderKnecht Syntax: "variant state;"
        items = self.add_renderknecht_style_strings(variant_set_str)
        if items:
            self.add_items(items)
            return

        # Text contains new line \n and or carriage return \n characters, replace with spaces
        if '\r\n' in variant_set_str:
            variant_set_str = variant_set_str.replace('\r\n', ' ')
        if '\n' in variant_set_str:
            variant_set_str = variant_set_str.replace('\n', ' ')

        items = self.add_multiple_line_style_strings(variant_set_str, variant_str)
        if items:
            self.add_items(items)
            return

        # Get placeholder text if field is empty
        if variant_set_str == '':
            variant_set_str = self.ui.plainTextEdit_addVariant_Setname.placeholderText()
        if variant_str == '':
            variant_str = self.ui.plainTextEdit_addVariant_Variant.placeholderText()

        # Add tree item and sort order
        new_item = self.add_variant_item(variant_set_str, variant_str)
        self.add_items([new_item])

    def add_items(self, items):
        self.view.editor.create_top_level_rows(items)

    @staticmethod
    def add_variant_item(name: str, value: str, order: int=0) -> KnechtItem:
        data = [None for _ in Kg.column_range]
        data[Kg.ORDER], data[Kg.NAME], data[Kg.VALUE] = f'{order:03d}', name, value

        return KnechtItem(data=tuple(data))

    def add_renderknecht_style_strings(self, variant_set_str: str) -> Union[bool, List[KnechtItem]]:
        # Text contains semicolons, guess as old RenderKnecht Syntax: "variant state;"
        if ';' in variant_set_str:
            items = list()
            for var in variant_set_str.split(';'):
                var = var.split(' ', 2)

                if var[0] != '':
                    if len(var) > 1:
                        if var[1] != '':
                            new_item = self.add_variant_item(var[0], var[1], len(items))
                            items.append(new_item)

            return items
        return False

    def add_multiple_line_style_strings(self, variant_set_str: str, variant_str: str) -> Union[bool, List[KnechtItem]]:
        # Text contains spaces, create multiple lines
        if ' ' in variant_set_str:
            items = list()
            for variant in variant_set_str.split(' '):
                if variant != '':
                    new_item = self.add_variant_item(variant, variant_str, len(items))
                    items.append(new_item)

            return items
        return False

    def update_actions(self):
        self.ui.plainTextEdit_addVariant_Variant.clear()
        self.ui.plainTextEdit_addVariant_Setname.clear()
