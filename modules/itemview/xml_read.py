from pathlib import Path
from typing import Union

from lxml import etree as Et

from modules.itemview.item import KnechtItem
from modules.itemview.model_globals import KnechtModelGlobals as Kg, KnechtModelXmlTags as KgTags
from modules.itemview.xml_id import KnechtXmlId
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


def path_is_xml_string(file: Union[Path, str]) -> bool:
    if isinstance(file, Path):
        return False

    # Skip additional checks for now
    return True


class KnechtOpenXml:
    """
        Parse Xml document and return a root_item
    """
    @staticmethod
    def read_xml(file):
        reader = KnechtXmlReader()
        root_item = reader.read_xml(file)
        return root_item, reader.error


class KnechtXmlReader:
    """ Read RenderKnecht Xml

        :param: error: String containing the error message for the user
    """

    def __init__(self):
        # Helper class to convert and create QUuids
        self.xml_id = KnechtXmlId()
        # Temporary item stores -currently- iterated preset item
        self.__preset_item = None
        # Loaded items temporary root item
        self.root_item = KnechtItem()
        # Store error message
        self.error = str()

    def read_xml(self, file: Union[Path, str, bytes]) -> KnechtItem:
        """ Read RenderKnecht Xml and return list of KnechtItem's

            Stores Xml read errors in class attribute errors.

            :param: file: Xml file to load or utf-8 encoded Xml string
            :type: file: Path or str
            :rtype: KnechtItem: KnechtItem Root Node
            :returns: tree root node
        """
        xml = None

        if path_is_xml_string(file):
            try:
                xml = Et.fromstring(file)
            except Exception as e:
                LOGGER.error('Error parsing Xml string data: %s', e)
                self.set_error(0)
                return self.root_item

        if xml is None:
            try:
                xml = Et.parse(file.as_posix())
            except Exception as e:
                LOGGER.error('Error parsing Xml document:\n%s', e)
                self.set_error(0)
                return self.root_item

        if not self._validate_renderknecht_xml(xml):
            self.set_error(1)
            return self.root_item

        # Transfer Xml to self.root_item
        self._xml_to_items(xml)

        if not self.root_item.childCount():
            self.set_error(2)

        # Return the list of item data
        return self.root_item

    def _xml_to_items(self, xml):
        for e in xml.iterfind('./*//'):
            self._read_node(e)

    def _read_node(self, node: Et.Element):
        # Re-write order with leading zeros
        if 'order' in node.attrib.keys():
            node.set('order', f'{int(node.attrib["order"]):03d}')

        # Backwards compatible, value stored in tag text
        if node.tag == KgTags.variant_tag and node.text:
            node.set('value', node.text)

        if node.tag in KgTags.preset_tags:
            # Create preset item: node, parent
            self.__preset_item = self._create_tree_item(node)

        elif node.tag == KgTags.render_preset_tag:
            self.__preset_item = self._create_tree_item(node)

        elif node.tag in KgTags.separator_tags:
            self._create_tree_item(node)

        elif node.tag in KgTags.sub_separator_tags:
            node.attrib['type'] = 'sub_separator'
            self._create_tree_item(node, self.__preset_item)

        elif node.tag in KgTags.render_setting_tags:
            self._create_tree_item(node, self.__preset_item)

        elif node.tag in KgTags.variants_tags:
            if node.getparent().tag == Kg.xml_dom_tags['level_1']:
                # Parse orphans aswell for session load / variants widget
                self._create_tree_item(node)
            else:
                # Create variant / reference with parent: last preset_item
                self._create_tree_item(node, self.__preset_item)

    def _create_tree_item(self, node, parent_item: KnechtItem=None) -> KnechtItem:
        data = self._data_from_element_attribute(node)

        if parent_item is None:
            child_position = self.root_item.childCount()
            self.root_item.insertChildren(child_position, 1, data)
            parent_item = self.root_item.child(child_position)

            self.xml_id.update_preset_uuid(node, parent_item)
            return parent_item

        position = parent_item.childCount()
        result = parent_item.insertChildren(position, 1, data)

        if not result:
            LOGGER.error('Could not insert child %s %s', position, parent_item.childCount())
            return parent_item

        self.xml_id.update_reference_uuid(node, parent_item.child(position))
        return parent_item

    def set_error(self, error_type: int = 0):
        error_msg = {
            0: _('Das gewählte Xml Dokument ist kein gültiges Xml Dokument und konnte nicht gelesen werden.'),
            1: _('Das gewählte Xml Dokument enthält nicht die erwarteten Daten. Es ist kein RenderKnecht '
                 'kompatibles Xml Dokument.'),
            2: _('Das gewählte Xml Dokument ist gültig, enthält aber kein Daten.'),
            }

        self.error = error_msg[error_type]

    @staticmethod
    def _data_from_element_attribute(node) -> tuple:
        data = list()

        for key in Kg.column_keys:
            data.append(
                node.attrib.get(key) or ''
                )

        return tuple(data)

    @staticmethod
    def _validate_renderknecht_xml(xml):
        root = xml.find('.')
        if root.tag != Kg.xml_dom_tags['root']:
            LOGGER.error('Can not load Xml document. Expected xml root tag: %s, received: %s',
                         Kg.xml_dom_tags['root'], root.tag)
            return False
        return True
