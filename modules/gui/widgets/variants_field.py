from typing import List, Union

from PySide2.QtCore import QObject, QTimer, Slot

from modules.itemview.item import KnechtItem
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.knecht_camera import KnechtImageCameraInfo
from modules.log import init_logging

LOGGER = init_logging(__name__)


class VariantInputFields(QObject):
    lead_trail_remove = ('"', ' ', '_', '-', '\n')  # Leading/Trailing characters to remove

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

        # Remove trailing or leading spaces, line breaks etc.
        if variant_set_str[-1:] in self.lead_trail_remove:
            variant_set_str = variant_set_str[:-1]
        if variant_set_str[:1] in self.lead_trail_remove:
            variant_set_str = variant_set_str[1:]

        LOGGER.debug(variant_set_str)

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
        if ',' in variant_set_str:
            variant_set_str = variant_set_str.replace(',', ' ')

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

        # Clear Input field
        self.ui.plainTextEdit_addVariant_Setname.clear()
        self.ui.plainTextEdit_addVariant_Variant.clear()

    @staticmethod
    def add_variant_item(name: str, value: str, order: int=0) -> KnechtItem:
        data = [None for _ in Kg.column_range]
        data[Kg.ORDER], data[Kg.NAME], data[Kg.VALUE] = f'{order:03d}', name, value

        return KnechtItem(data=tuple(data))

    @staticmethod
    def _lookup_camera_items(variant_set: list, cam_info: dict) -> bool:
        """
            Update camera info if pasted knecht-style strings contain eg:
                rtt_Camera_FOV FOV CAMERA 12.1234;
                rtt_Camera_Position POS CAMERA 0.000 0.000 0.000;
                rtt_Camera_Orientation ORIENT CAMERA 0.00 0.00 0.00 180.1234;
        """
        cam_key = variant_set[0]
        cam_value = ' '.join([v for v in variant_set[1:]])[:-1]  # variant_set[1:] = ['FOV', 'CAMERA 12.123']
        cam_cmds = KnechtImageCameraInfo.rtt_camera_cmds
        if cam_key in cam_cmds:
            cam_rem = cam_cmds[cam_key].format('', '', '', '').rstrip(' ')  # 'FOV CAMERA {0}' -> 'FOV CAMERA'
            cam_value = cam_value.replace(cam_rem + ' ', '')  # 'FOV CAMERA 12.123' -> '12.123'

            # Update Camera Info dict
            cam_info[cam_key] = cam_value.replace(' ', ', ')  # 'rtt_camera_FOV': '12.123'
            return True
        return False

    def add_renderknecht_style_strings(self, variant_set_str: str) -> List[KnechtItem]:
        items, cam_info = list(), dict()
        # If text contains semicolons, guess as old RenderKnecht Syntax: "variant state;"
        if ';' not in variant_set_str:
            return items

        for var in variant_set_str.split(';'):
            var = var.split(' ', 2)

            if var[0] != '':
                if len(var) > 1:
                    if var[1] != '':
                        # -- Extract Camera Info
                        if self._lookup_camera_items(var, cam_info):
                            continue
                        # -- Extract Variant_Set Variant_Value
                        new_item = self.add_variant_item(var[0], var[1], len(items))
                        items.append(new_item)

        # Create camera item from extracted camera_info dict
        if cam_info:
            cam_item = self.view.editor.create.create_camera_item(f'pasted_Camera_{len(items):03d}', cam_info)
            items.append(cam_item)

        return items

    def add_multiple_line_style_strings(self, variant_set_str: str, variant_str: str) -> Union[bool, List[KnechtItem]]:
        # Text contains spaces, create multiple lines
        if ' ' in variant_set_str:
            items = list()
            for variant in variant_set_str.split(' '):
                if variant != '':
                    new_item = self.add_variant_item(variant, variant_str, len(items))
                    items.append(new_item)

            return items

        # PlmXml / LINC Style PR-Strings
        if variant_set_str.startswith('+'):
            items = list()
            for variant in variant_set_str[1:].split('+'):
                if variant != '':
                    new_item = self.add_variant_item(variant, variant_str, len(items))
                    items.append(new_item)

            return items

        return False

    def update_actions(self):
        self.ui.plainTextEdit_addVariant_Variant.clear()
        self.ui.plainTextEdit_addVariant_Setname.clear()
