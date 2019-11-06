from lxml import etree as Et

from modules.language import get_translation
from modules.log import init_logging
from modules.plmxml import ProductInstance
from modules.plmxml.globals import AS_CONNECTOR_XMLNS as AS_XMLNS
from modules.plmxml.objects import NodeInfo

LOGGER = init_logging(__name__)


# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


def find_text_attribute(child, attr_name) -> str:
    found_attribute = child.find(f'{AS_XMLNS}{attr_name}')
    if found_attribute is not None:
        return found_attribute.text
    else:
        return ""


def find_user_attributes_in_element(child):
    """ Helper to find the UserAttributeArray """
    user_attribute_dict = dict()
    user_attributes = child.find(f'{AS_XMLNS}UserAttributes')

    if user_attributes is None:
        return user_attribute_dict

    for ua in user_attributes:
        ua_key = ua.find(f'{AS_XMLNS}Key')
        ua_value = ua.find(f'{AS_XMLNS}Value')

        if ua_key is not None and ua_value is not None:
            user_attribute_dict[ua_key.text] = ua_value.text

    return user_attribute_dict


def get_node_info_from_element(e: Et._Element):
    """ Get NodeInfo from an XML element """
    linc_id = find_text_attribute(e, "LincId")
    name = find_text_attribute(e, "Name")
    parent_node_id = find_text_attribute(e, "ParentNodeId")
    node_info_type = find_text_attribute(e, "NodeInfoType")
    if node_info_type == "":
        node_info_type = "UNKNOWN"
    material_name = find_text_attribute(e, "MaterialName")
    user_attribute_array = find_user_attributes_in_element(e)
    as_id = find_text_attribute(e, 'AsId')

    p = ProductInstance(
        as_id=as_id, user_data=user_attribute_array, parent_node_id=parent_node_id, name=name, linc_id=linc_id
        )

    return NodeInfo(p, node_info_type=node_info_type, material_name=material_name)