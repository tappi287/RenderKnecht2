from pathlib import Path
from typing import Union

from PySide2.QtCore import QUuid
from lxml import etree as Et

from modules.itemview.item import KnechtItem
from modules.itemview.model import KnechtModel
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.itemview.xml_read import path_is_xml_string
from modules.itemview.xml_id import KnechtXmlId
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class KnechtSaveXml:
    """
        Save Xml document and return result and store errors
    """
    @staticmethod
    def save_xml(file, model):
        saver = KnechtXmlWriter()
        result = saver.save_model_to_xml(file, model)
        return result, saver.error


class KnechtXmlWriter:
    """ Save RenderKnecht2 Xml """

    def __init__(self):
        # Helper class to convert and create QUuids
        self.id_mgr = KnechtXmlId()
        # Store error message
        self.error = str()

    def save_model_to_xml(self, file: Union[Path, str], model: KnechtModel) -> bool:
        root = Et.Element(Kg.xml_dom_tags['root'])
        Et.SubElement(root, Kg.xml_dom_tags['origin'])
        Et.SubElement(root, Kg.xml_dom_tags['settings'])
        preset_elements = Et.SubElement(root, Kg.xml_dom_tags['level_1'])

        for item in model.root_item.iter_children():
            preset_elements.append(self.elements_from_item(item))

        if not len(root):
            LOGGER.error('Found no elements to save')
            return False

        if path_is_xml_string(file):
            return Et.tostring(root, xml_declaration=False, encoding='UTF-8', pretty_print=False)
        else:
            LOGGER.info('Saving to: %s', file.as_posix())
            try:
                with open(file.as_posix(), 'wb') as f:
                    f.write(Et.tostring(root, xml_declaration=True, encoding='UTF-8', pretty_print=True))
                return True
            except Exception as e:
                LOGGER.error('Error writing file:\n%s', e)
                self.error = _('Fehler beim schreiben der Datei: {}').format(e)

        return False

    def elements_from_item(self, item: KnechtItem):
        element = self._create_element_from_item(item)

        for child in item.iter_children():
            e = self._create_element_from_item(child)

            if e is not None:
                element.append(e)

        return element

    def _create_element_from_item(self, item) -> Et.Element:
        tag = Kg.xml_tag_by_user_type[item.userType]  # Tag from UserType
        attrib = dict()

        for key, value in zip(Kg.column_keys, item.data_list()):
            if isinstance(value, QUuid):
                # Convert QUuid back to integer Id string
                value = self.id_mgr.save_uuid(value)

            if value and value is not None:
                attrib[key] = value

        return Et.Element(tag, attrib)
