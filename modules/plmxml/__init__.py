import time
from pathlib import Path
from typing import Dict, Iterator

from lxml import etree as Et

from modules.gui.widgets.path_util import path_exists
from modules.plmxml.globals import PLM_XML_NAMESPACE, PRODUCT_INSTANCE_TAGS, PRODUCT_INSTANCE_XPATH, USER_DATA_XPATH, \
    LOOK_LIBRARY_INSTANCE_NAME
from modules.plmxml.objects import LookLibrary, NodeInfo
from modules.plmxml.utils import pr_tags_to_reg_ex

from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class PlmXml:
    debug = False

    def __init__(self, file: Path):
        self.file = file
        self.nodes: Dict[str, NodeInfo] = dict()
        self.look_lib = LookLibrary()
        self.error = ''
        self._is_valid = False

        self.parse_plm_xml()

    @property
    def is_valid(self):
        return self._is_valid

    def iterate_configurable_nodes(self) -> Iterator[NodeInfo]:
        for p in self.nodes.values():
            if p.pr_tags:
                yield p

    def _read_product_instance_element(self, n):
        """ Read a single product instance node

        :param Et._Element n: Xml node to read values from
        :return:
        """
        # -- Get ProductInstance Attributes
        instance_id = n.attrib.get(PRODUCT_INSTANCE_TAGS.get('id'))
        name = n.attrib.get(PRODUCT_INSTANCE_TAGS.get('name'))
        part_ref = n.attrib.get(PRODUCT_INSTANCE_TAGS.get('part_ref'))

        if instance_id in self.nodes:
            LOGGER.warning('ProductInstance with id: %s already exists and will be overwritten!', instance_id)

        # -- Create LookLibrary if ProductInstance with name "LookLibrary" found
        if name == LOOK_LIBRARY_INSTANCE_NAME:
            self.look_lib.read_look_lib_instance(n)
            return

        # -- Find UserData/UserValue's
        user_data = self._read_node_user_data(n)

        # -- Store ProductInstance as NodeInfo
        self.nodes[instance_id] = NodeInfo(
            plmxml_id=instance_id, part_ref=part_ref, name=name, user_data=user_data
            )

        # -- Print result
        if self.debug:
            LOGGER.debug(f'{instance_id}: {name}, {part_ref}, {user_data.get("PR_TAGS")}, '
                         f'{pr_tags_to_reg_ex(self.nodes[instance_id].pr_tags)}')

    @staticmethod
    def _read_node_user_data(n: Et._Element):
        user_data = dict()

        for user_node in n.iterfind(USER_DATA_XPATH):
            key = user_node.attrib.get('title')
            value = user_node.attrib.get('value')
            user_data[key] = value

        return user_data

    def parse_plm_xml(self):
        if not path_exists(self.file):
            self.error = _(_('PlmXml Datei wurde nicht gefunden.'))

        # --- parse Xml tree ---
        parse_start = time.time()
        try:
            tree = Et.parse(self.file.as_posix())
        except Exception as e:
            self.error = _('Fehler beim Parsen der PlmXml:\n{}').format(e)
            LOGGER.error(self.error)
            return
        parse_end = time.time()

        # --- get root node ---
        root: Et.Element = tree.getroot()
        # --- Prepare node storage ---
        self.nodes = dict()

        # -- Read product instance nodes
        for n in root.iterfind(PRODUCT_INSTANCE_XPATH):
            self._read_product_instance_element(n)

        index_end = time.time()

        # -- Report Materials
        if self.debug:
            for material, material_variant in self.look_lib.iterate_materials():
                LOGGER.debug(f'{material.name} - {material_variant.pr_tags} -> {material_variant.name}')

        # --- Look for conflicting pr_tag look target variants
        self.look_lib.report_conflicting_targets()

        # -- Set this instance as valid
        if self.nodes and self.look_lib.is_valid:
            self._is_valid = True

        # -- Report result
        LOGGER.debug('Namespace Map: %s', root.nsmap)
        LOGGER.info(f'Parsed file {self.file.name} in {parse_end - parse_start:.5f}s')
        LOGGER.info(f'Indexed {len(self.nodes)} ProductInstances from which '
                    f'{len([_id for _id, pi in self.nodes.items() if pi.pr_tags is not None])} '
                    f'contained PR_TAGS in {index_end - parse_end:.5f}s')

        LOGGER.info(f"Found LookLibrary with {len(self.look_lib.materials)} materials and "
                    f"{len([l for m, l in self.look_lib.iterate_materials()])} Material variants.")
