import re
from typing import Dict, Union, Tuple
from xml.etree import ElementTree as Et

from lxml import etree as Et

from modules.plmxml import PLM_XML_NAMESPACE
from modules.plmxml.utils import pr_tags_to_reg_ex, create_attribute_child_tag, \
    create_user_attributes_elements_from_dict, find_text_attribute, find_user_attributes_in_element
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class MaterialVariant:
    def __init__(self, name, pr_tags, desc):
        self.name = name
        self.pr_tags = pr_tags
        self.desc = desc


class MaterialTarget:
    def __init__(self, name, material_variants: list):
        self.name = name
        self.variants: list = material_variants

        self._visible_variant = None

    @property
    def visible_variant(self) -> Union[None, MaterialVariant]:
        return self._visible_variant

    @visible_variant.setter
    def visible_variant(self, value: Union[None, MaterialVariant]):
        self._visible_variant = value


class LookLibrary:
    debug_conflicts = False  # Will intentionally place some conflicts
    look_lib_xpath = f"{PLM_XML_NAMESPACE}UserData/{PLM_XML_NAMESPACE}UserValue"

    def __init__(self):
        """ Plm Xml Look Library

        """
        self.materials: Dict[str, MaterialTarget] = dict()
        self.conflicting_targets = list()

        self._is_valid = False

    @property
    def is_valid(self):
        return self._is_valid

    def reset(self):
        """ Call this in front of every configuration! Will reset Target->Source configuration """
        for target in self.materials.values():
            target.visible_variant = None

    def iterate_materials(self) -> Tuple[MaterialTarget, MaterialVariant]:
        """ Iterate the material variants of every target material """
        for name, material in self.materials.items():
            for material_variant in material.variants:
                yield material, material_variant

    def iterate_active_targets(self):
        """ Iterate all target materials that have a visible variant """
        for material in self.materials.values():
            if material.visible_variant:
                yield material

    def report_conflicting_targets(self) -> list:
        self._get_target_conflicts()

        if not self.conflicting_targets:
            LOGGER.debug('LookLibrary contained no conflicting pr_tag/target combination.')
        else:
            for err in self.conflicting_targets:
                LOGGER.error('LookLibrary conflict: %s', err)

        return self.conflicting_targets

    def _get_target_conflicts(self):
        """ Test if material variants have multiple matches within their target material
            Therefore multiple variants would be valid during a configuration.

            Eg. Variant1 matches against AB
                Variant2 matches against AB+DEF

        :return:
        """
        for name, material in self.materials.items():
            pr_tags, conflicting_variants = set(), list()

            for variant in material.variants:
                for pr_tag in pr_tags:
                    match = re.search(pr_tags_to_reg_ex(variant.pr_tags), pr_tag)
                    if match:
                        conflicting_variants.append(f'{variant.name} - {variant.pr_tags} '
                                                    f'is also matching {match.group(0)}')
                pr_tags.add(variant.pr_tags)

            if conflicting_variants:
                self.conflicting_targets.append(f'{name} variants: {" ".join(conflicting_variants)}')

    def read_look_lib_instance(self, look_library_node) -> bool:
        """ Read a ProductInstance Xml node that contains the LookLibrary

        :param Et._Element look_library_node:
        :return:
        """
        look_nodes = look_library_node.findall(self.look_lib_xpath)
        self._is_valid = False

        if look_nodes is None:
            return False

        for look_node in look_nodes:
            look_value = look_node.attrib.get('value') or ''

            material = self._get_material_from_value(look_value)

            if material:
                self.materials[material.name] = material

        if self.materials:
            self._is_valid = True
            return True

        return False

    @staticmethod
    def _get_material_from_value(look_value: str) -> Union[None, MaterialTarget]:
        """
        Example
        E_xxxxxx_Example~  [AB-031~ ALLE+ABC; ~ KURZ BESCHREIBUNG] [ABC001~ ALLE+DEF; ~ LANG BESCHREIBUNG]

            1. Match target name: ^(?:[a-z][a-z0-9_]*)
               -> E_xxxxxx_Example

            2. Split at brackets: \\[(.*?)\\]
               -> [AB-031..., ABC001...]

            3. Split every bracket at OR combination of whitespace+tilde: \s~\s|~\s
               -> [AB-031, ALLE+ABC;, KURZ BESCHREIBUNG]

        :param str look_value:
        :return:
        """
        # Match the target name
        target_name = re.match('^(?:[a-zA-Z][a-zA-Z0-9_]*)', look_value)
        if not target_name:
            return

        target_name = target_name.group(0)

        # Split at square brackets
        variants = re.findall('\\[(.*?)\\]', look_value)
        if not variants:
            return

        material_variants = list()

        for v in variants:
            m = re.split('\s~\s|~\s', v)

            if not m or len(m) != 3:
                continue

            material_name, pr_tags, desc = m
            material_variants.append(MaterialVariant(material_name, pr_tags, desc))

        if LookLibrary.debug_conflicts:
            # Add conflicting test material
            material_variants.append(MaterialVariant('TestMaterial', 'FZ+N0L;', ''))

        return MaterialTarget(target_name, material_variants)


class NodeInfo:
    class Types:
        enumerations = ['UNKNOWN', 'SHAPE', 'GROUP', 'SPOTLIGHT', 'POINTLIGHT', 'DIRECTIONALLIGHT', 'LOCALSURROUNDING',
                        'SWITCH', 'LOD', 'FILE', 'LOCATOR', 'LIGHTCOLLECTOR', 'SOUND', 'LIGHTEMITTER', 'FX', 'CAMERA',
                        'BODY', 'SHELL']

    def __init__(self, plmxml_id: str='', linc_id: str='', part_ref: str='', name: str='', user_data: dict=None,
                 as_id: str='', parent_node_id: str='', node_info_type: str='UNKNOWN', material_name: str=''):
        """ Represents ProductInstances in PlmXml and NodeInfo nodes in AsConnector

        :param str plmxml_id: PlmXml document xml ProductInstance id attribute
        :param str linc_id: PlmXml UserData LINC_ID
        :param str part_ref: PlmXml document xml ProductInstance partRef attribute
        :param str name: PlmXml document xml ProductInstance name attribute
        :param user_data: PlmXml UserData/UserValue as dict
        :param str as_id: AsConnector ID when node was read out from AsConnector REST Api, seems to be session bound
        :param str parent_node_id: when node was read out from AsConnector REST Api
        :param str node_info_type: One of Types.enumerations, maybe read this out from PlmXml UserData LINC_NODE_TYPE!?
        :param material_name: when node was read out from AsConnector REST Api
        """
        self.user_data = user_data if user_data else dict()
        self.plmxml_id = plmxml_id
        if linc_id:
            self.linc_id = linc_id
        else:
            self.linc_id = self.user_data.get('LINC_ID') or ""
        self.part_ref = part_ref
        self.name = name
        self.as_id = as_id
        self.parent_node_id = parent_node_id
        self.type = self._validate_node_info_type(node_info_type)
        self.material_name = material_name

        self._visible = False

    @property
    def visible(self):
        return self._visible

    @visible.setter
    def visible(self, value: bool):
        self._visible = value

    @property
    def element(self):
        return self._create_node_element()

    @property
    def pr_tags(self):
        return self.user_data.get('PR_TAGS')

    def _validate_node_info_type(self, value: str):
        if value not in self.Types.enumerations:
            LOGGER.warning('NodeInfo created with invalid type setting: %s; Setting default value: %s',
                           value, self.Types.enumerations[0])
            return self.Types.enumerations[0]
        else:
            return value

    def _create_node_element(self):
        """ Create an AsConnector NodeInfo Xml element from this node info instance """
        # -- NodeInfo root node
        node_info_element = Et.Element('NodeInfo')

        # -- Create Attribute Elements
        # <NodeInfo><tag>value</tag></NodeInfo>
        for tag, value in [('AsId', self.as_id), ('ParentNodeId', self.parent_node_id),
                           ('LincId', self.linc_id), ('Name', self.name), ('NodeInfoType', self.type),
                           ('MaterialName', self.material_name)]:
            create_attribute_child_tag(node_info_element, tag, value)

        # -- Create UserAttributes Element
        # <NodeInfo>
        #   <UserAttributes><UserAttribute><Key>key</Key><Value>value</Value></UserAttribute></UserAttributes>
        # </NodeInfo>
        create_user_attributes_elements_from_dict(node_info_element, self.user_data)

        return node_info_element

    @staticmethod
    def get_node_from_element(e: Et._Element):
        """ Get NodeInfo instance from an AsConnectorResponse XML element """
        linc_id = find_text_attribute(e, "LincId")
        name = find_text_attribute(e, "Name")
        parent_node_id = find_text_attribute(e, "ParentNodeId")
        node_info_type = find_text_attribute(e, "NodeInfoType")

        if node_info_type == "":
            node_info_type = "UNKNOWN"

        material_name = find_text_attribute(e, "MaterialName")
        user_attribute_array = find_user_attributes_in_element(e)
        as_id = find_text_attribute(e, 'AsId')

        return NodeInfo(as_id=as_id, user_data=user_attribute_array, parent_node_id=parent_node_id, name=name,
                        linc_id=linc_id, node_info_type=node_info_type, material_name=material_name)
