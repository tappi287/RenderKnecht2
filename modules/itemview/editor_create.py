from typing import List, Union

from PySide2.QtCore import QObject, Qt, QTimer

from modules.gui.clipboard import TreeClipboard
from modules.idgen import KnechtUuidGenerator as Kid, KnechtUuidGenerator
from modules.itemview.item import KnechtItem
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.knecht_camera import KnechtImageCameraInfo
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class ItemTemplates:
    # -- Reset --
    reset = KnechtItem(None, ('000', 'Reset', '', 'reset'))
    reset.append_item_child(
        KnechtItem(None, ('000', 'reset', 'on', '', '', '',
                          _('Sollte einen im Modell vorhanden Reset Schalter betätigen'))),
        )
    reset.append_item_child(
        KnechtItem(None, ('001', 'reset', 'off', '', '', '',
                          _('Sollte einen im Modell vorhanden Reset Schalter betätigen'))),
        )
    reset.append_item_child(
        KnechtItem(None, ('002', 'RTTOGLRT', 'on', '', '', '',
                          _('Benötigte Optionen müssen nach dem Reset erneut geschaltet werden.'))),
        )

    # -- Trim --
    trim = KnechtItem(None, ('000', 'OEM Derivat Form Trimline Engine', '', 'trim_setup'))
    trim.append_item_child(
        KnechtItem(None, ('000', _('Motorschalter'), 'on', '', '', '', _('Variante des Modells')))
        )
    trim.append_item_child(
        KnechtItem(None, ('001', _('Serien_Optionen'), 'on', '', '', '', _('Varianten der Serienumfänge')))
        )

    # -- Package --
    package = KnechtItem(None, ('000', _('Paket'), '', 'package'))
    package.append_item_child(
        KnechtItem(None, ('000', _('Paket_Variante'), 'on', '', '', '', _('Varianten der Paket Option'))),
        )

    # -- ViewSet --
    viewset = KnechtItem(None, ('000', 'Viewset', '', 'viewset'))
    viewset.append_item_child(
        KnechtItem(None, ('000', '#_Shot', 'Shot_00', '', '', '', _('Schalter des Shot Varianten Sets'))),
        )

    preset = KnechtItem(None, ('000', 'User_Preset', '', Kg.type_keys[Kg.preset]))

    # -- Render Preset --
    render = KnechtItem(None, ('000', 'RenderPreset', '', Kg.type_keys[Kg.render_preset]))
    render.append_item_child(
        KnechtItem(None, ('000', 'Anti-Aliasing Samples', '512', 'sampling', '', '',
                          _('Setzt das globale Sampling Level. Benutzt Clamping Einstellungen der geladenen Szene!'))))
    render.append_item_child(
        KnechtItem(None, ('001', _('Datei Erweiterung'), '.hdr', 'file_extension', '', '',
                          _('Setzt die Ausgabe Dateiendung. HDR wird als 8bit ausgegeben und '
                            'berücksichtigt Viewport Display Adaption.')))
        )
    render.append_item_child(
        KnechtItem(None, ('002', _('Auflösung'), '2560 1920', 'resolution', '', '',
                          _('Auflösung kann auch manuell, mit einem Leerzeichen getrennt, eingegeben werden: X Y')))
        )

    # -- FaKom Trim --
    fakom_trim = KnechtItem(None, ('000', 'FaKom Modell PR_SIB_VOS_LUM', '', 'fakom_setup'))
    fakom_children = list()
    fakom_children.append(KnechtItem(None, ('000', _('XX_Farbschluessel'), 'on', '', '', '',
                                            _('Zweistelliger Farbschluessel'))))
    fakom_children.append(KnechtItem(None, ('001', _('PRN_Sitzbezug'), 'on', 'SIB', '', '', _('Sitzbezug Option'))))
    fakom_children.append(KnechtItem(None, ('002', _('PRN_Vordersitze'), 'on', 'VOS', '', '', _('Sitzart Option'))))
    fakom_children.append(KnechtItem(None, ('003', _('PRN_Lederumfang'), 'on', 'LUM', '', '', _('Lederpaket Option'))))
    for child in fakom_children:
        fakom_trim.append_item_child(child)

    # -- FaKom Option --
    fakom_option = KnechtItem(None, ('000', 'FaKom Model PR_SIB_VOS_LUM Option', '', 'fakom_option'))
    for child in fakom_children:
        fakom_option.append_item_child(child)

    # -- Output Item --
    output = KnechtItem(None, ('000', _('Ausgabe Pfad'), _('<Kein Pfad gesetzt>'), 'output_item'))

    # -- PlmXml Item --
    plmxml = KnechtItem(None, ('000', _('PlmXml Datei'), _('<Kein Pfad gesetzt>'), 'plmxml_item'))

    # -- Separator --
    separator = KnechtItem(None, ('000',  '', '', 'separator'))


class KnechtEditorCreate(QObject):

    def __init__(self, editor):
        """ KnechtEditor item creation helper methods

        :param modules.itemview.editor.KnechtEditor editor:
        """
        super(KnechtEditorCreate, self).__init__(editor)
        self.editor = editor
        self.item_count = 0

    def create_camera_item(self, name: str, camera_info: dict):
        item = KnechtItem(None, ('', name, '', 'camera_item', '', KnechtUuidGenerator.create_id(),))

        for idx, (k, v) in enumerate(camera_info.items()):
            item.append_item_child(
                KnechtItem(item, (f'{idx:03d}', k, v, '', '', '', KnechtImageCameraInfo.rtt_camera_desc.get(k) or '', ))
                )
        return item

    def create_preset_from_items(self, child_items: List[KnechtItem]):
        """ Create a preset item from given child items

        :param child_items: The items from which to create the preset
        :return:
        """
        # - Remove Reset items
        child_items = self.editor.util.remove_pasted_resets(child_items, 1)
        # -- Create User Preset --
        return self.add_item(ItemTemplates.preset, child_items, create_id=True)

    def create_render_preset_from_items(self, child_items: List[KnechtItem]):
        # - Remove Reset items
        child_items = self.editor.util.remove_pasted_resets(child_items, 1)
        # -- Create Render Preset --
        return self.add_item(ItemTemplates.render, child_items)

    def add_item(self, item: KnechtItem, children: Union[None, List] = None, create_id: bool = False):
        # Create a unique copy
        item = item.copy(True, None)

        # Update Name
        if item.data(Kg.TYPE) == Kg.type_keys[Kg.separator]:
            item.setData(Kg.NAME, '')
        else:
            item.setData(Kg.NAME, f'{item.data(Kg.NAME)}_{self.item_count:03d}')
            self.item_count += 1

        # Create unique item id
        if create_id:
            item.setData(Kg.ID, Kid.create_id())

        # Add children
        for child_item in children or []:
            child_item.setData(Kg.ORDER, f'{item.childCount():03d}', Qt.DisplayRole)
            item.append_item_child(child_item)

        # Get order data
        current_src_index, _ = self.editor.get_current_selection()
        order = self.editor.util.get_order_data(current_src_index)

        self.editor.create_top_level_rows([item], at_row=order)
        return item
