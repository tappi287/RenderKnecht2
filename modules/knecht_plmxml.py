import re
import time
from pathlib import Path
from queue import Queue
from typing import Dict, Tuple, Union, List

from lxml import etree as Et

from modules.globals import DEV_LOGGER_NAME, PLM_XML_NAMESPACE
from modules.gui.widgets.path_util import path_exists
from modules.language import get_translation
from modules.log import init_logging, setup_logging
from private.plmxml_example_data import example_pr_string, plm_xml_file

LOGGER = init_logging(__name__)


# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


def pr_tags_to_reg_ex(pr_tags: Union[None, str]) -> str:
    """ Example:
            +ABC/DEF/A11+K11;

            ^((?=.*\bABC\b)|(?=.*\bDEF\b)|(?=.*\bA11\b))(?=.*\bK11\b).*$

    :param str pr_tags: String of PR_TAGS
    :return: Return a regex pattern that can be matched against a configuration string
    """
    pattern = ''

    if not pr_tags or pr_tags is None:
        return pattern

    # --- Split tags <tag>;<tag> ---
    # every tag will be matched against the full string
    # ^<tag>.*$
    #
    # multiple tags will be matched with OR
    # ^<tag>.*$|^<tag>.*$
    #
    for tag in pr_tags.split(';'):
        tag_pattern = ''

        # Split PR inside a tag with AND
        # (?=.*\b<PR>\b)(?=.*\b<PR>\b)
        #               ^and
        #
        for w in tag.split('+'):
            r_ex, s_ex = '', ''

            # Split OR '/' combinations
            # (?=.*\b<PR>\b)
            # move multiple OR combinations into their own capture group
            # ((?=.*\b<PR>\b)|(?=.*\b<PR>\b))
            # ^any of these will match
            #
            if '/' in w:
                for s in w.split('/'):
                    s_ex += f'(?=.*\\b{s}\\b)|'
                s_ex = f'({s_ex[:-1]})'
            elif w:
                r_ex = f'(?=.*\\b{w}\\b)'

            tag_pattern += r_ex + s_ex

        if tag_pattern:
            # Combine all <tag> as OR combination
            # each matching against the whole string ^<tag_pattern>.*$
            #
            pattern += f'^{tag_pattern}.*$|'

    # Remove trailing OR '|'
    #
    return pattern[:-1]


class MaterialVariant:
    def __init__(self, name, pr_tags, desc):
        self.name = name
        self.pr_tags = pr_tags
        self.desc = desc


class MaterialTarget:
    def __init__(self, name, material_variants: Dict[str, MaterialVariant]):
        self.name = name
        self.variants: Dict[str, MaterialVariant] = material_variants

        self._visible_variant = None

    @property
    def visible_variant(self) -> Union[None, str]:
        return self._visible_variant

    @visible_variant.setter
    def visible_variant(self, value: Union[None, str]):
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

    def iterate_materials(self) -> Tuple[MaterialTarget, MaterialVariant]:
        """ Iterate the material variants of every target material

        :return:
        """
        for name, material in self.materials.items():
            for variant_name, material_variant in material.variants.items():
                yield material, material_variant

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

            for variant_name, variant in material.variants.items():
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

        material_variants: Dict[str, MaterialVariant] = dict()
        material_name = ''

        for v in variants:
            m = re.split('\s~\s|~\s', v)

            if not m or len(m) != 3:
                continue

            material_name, pr_tags, desc = m
            material_variants[material_name] = MaterialVariant(material_name, pr_tags, desc)

        if LookLibrary.debug_conflicts:
            # Add conflicting test material
            material_variants[material_name] = MaterialVariant('TestMaterial', 'FZ+N0L;', '')

        return MaterialTarget(target_name, material_variants)


class ProductInstance:
    def __init__(self, _id='', part_id='', name='', pr_tags=''):
        self.part_id = part_id
        self.id = _id
        self.name = name
        self.pr_tags = pr_tags

        self._visible: bool = False

    @property
    def visible(self):
        return self._visible

    @visible.setter
    def visible(self, value: bool):
        self._visible = value


class PlmXml:
    debug = False
    _ns = PLM_XML_NAMESPACE

    product_instance_tags = {
        'part_id': 'partRef',
        'id': 'id',
        'name': 'name',
        'look_library_instance_name': 'LookLibrary',
        # Xpath for <PLMXML/root>/<ProductDef>/<InstanceGraph>/<ProductInstance>
        'xpath': f'{_ns}ProductDef/{_ns}InstanceGraph/{_ns}ProductInstance',
        # Xpath for child node <ProductInstance>/<UserData>/<UserValue title="PR_TAGS">
        'pr_tags_xpath': f"{_ns}UserData/{_ns}UserValue[@title='PR_TAGS']",
        }

    def __init__(self, file: Path):
        self.file = file
        self.product_instances: Dict[str, ProductInstance] = dict()
        self.look_lib = LookLibrary()
        self.error = ''
        self._is_valid = False

        self.read_product_instances()

    @property
    def is_valid(self):
        return self._is_valid

    def _read_product_instance_node(self, n):
        """ Read a single product instance node

        :param Et._Element n: Xml node to read values from
        :return:
        """
        # -- Get ProductInstance Attributes
        instance_id = n.attrib.get(self.product_instance_tags.get('id'))
        name = n.attrib.get(self.product_instance_tags.get('name'))
        part_id = n.attrib.get(self.product_instance_tags.get('part_id'))

        if instance_id in self.product_instances:
            LOGGER.warning('ProductInstance with id: %s already exists and will be overwritten!', instance_id)

        # -- Create LookLibrary if ProductInstance with name "LookLibrary" found
        if name == self.product_instance_tags.get('look_library_instance_name'):
            self.look_lib.read_look_lib_instance(n)

        # -- Find PR_TAGS in UserData/UserValue
        pr_tags = None
        user_node = n.find(self.product_instance_tags.get('pr_tags_xpath'))
        if user_node is not None:
            pr_tags = user_node.attrib.get('value')

        # -- Store product instance
        self.product_instances[instance_id] = ProductInstance(_id=instance_id, part_id=part_id, name=name,
                                                              pr_tags=pr_tags)

        # -- Print result
        if self.debug:
            LOGGER.debug(f'{instance_id}: {name}, {part_id}, {pr_tags}, '
                         f'{pr_tags_to_reg_ex(self.product_instances[instance_id].pr_tags)}')

    def read_product_instances(self):
        if not path_exists(self.file):
            self.error = _('The PlmXml file could not be found.')

        # --- parse Xml tree ---
        parse_start = time.time()
        try:
            tree = Et.parse(self.file.as_posix())
        except Exception as e:
            self.error = f'Error parsing PlmXml:\n{e}'
            LOGGER.error(self.error)
            return
        parse_end = time.time()

        # --- get root node ---
        root: Et.Element = tree.getroot()
        # --- Prepare node storage ---
        self.product_instances = dict()

        # -- Read product instance nodes
        for n in root.iterfind(self.product_instance_tags.get('xpath')):
            self._read_product_instance_node(n)

        index_end = time.time()

        # -- Report Materials
        if self.debug:
            for material, material_variant in self.look_lib.iterate_materials():
                LOGGER.debug(f'{material.name} - {material_variant.pr_tags} -> {material_variant.name}')

        # --- Look for conflicting pr_tag look target variants
        self.look_lib.report_conflicting_targets()

        # -- Set this instance as valid
        if self.product_instances and self.look_lib.is_valid:
            self._is_valid = True

        # -- Report result
        LOGGER.debug('Namespace Map: %s', root.nsmap)
        LOGGER.info(f'Parsed file {self.file.name} in {parse_end - parse_start:.5f}s')
        LOGGER.info(f'Indexed {len(self.product_instances)} ProductInstances from which '
                     f'{len([_id for _id, pi in self.product_instances.items() if pi.pr_tags is not None])} '
                     f'contained PR_TAGS in {index_end - parse_end:.5f}s')

        LOGGER.info(f"Found LookLibrary with {len(self.look_lib.materials)} materials and "
                    f"{len([l for m, l in self.look_lib.iterate_materials()])} Material variants.")


class AsConnectorRequest:
    """
        AsConnector REST Api2

        DeltaGen Port: 1234
        url: http://127.0.0.1:1234/v2///<METHOD-TYPE>/<METHOD>
        eg.: http://127.0.0.1:1234/v2///material/connecttotargets

        request:
        <?xml version="1.0" encoding="utf-8"?>
        <{method_type}{method_camel_case}Request xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns="urn:authoringsystem_v2">
            <{parameter}>
                {value}
            </{parameter}>
        </{method_type}{method_camel_case}Request>
    """

    xmlns = "urn:authoringsystem_v2"
    xsd = "http://www.w3.org/2001/XMLSchema"
    xsi = "http://www.w3.org/2001/XMLSchema-instance"

    ns_map = {'xsd': xsd, 'xsi': xsi, None: xmlns}

    def __init__(self):
        self._request = None

    @property
    def request(self):
        return self._request

    @request.setter
    def request(self, value: Et._Element):
        self._request = value

    def create_request_element(self, method_type, method_name) -> Et._Element:
        """ Create the request root node

            {method_type}{method_camel_case}Request {namespace}

            ->

            <TypeMethodNameRequest xmlns:xsd="http://www.w3.org/2001/XMLSchema"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns="urn:authoringsystem_v2">

        :param str method_type:
        :param str method_name:
        :return:
        """
        return Et.Element(f'{method_type}{method_name}Request', nsmap=self.ns_map)

    def create_material_connect_request(self,
                                        target_materials: List[MaterialTarget],
                                        use_copy_method: bool=False,
                                        replace_target_name: bool=False
                                        ):
        """ Create a Material:ConnectToTarget Request

            <?xml version="1.0" encoding="utf-8"?>
            <MaterialConnectToTargetsRequest xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns="urn:authoringsystem_v2">
                <materialNames>
                    <string>
                        ABC001
                    </string>
                </materialNames>
                <targetNames>
                    <string>
                        E_ABC000_Default
                    </string>
                </targetNames>
                <useCopyMethod>
                    false
                </useCopyMethod>
                <replaceTargetName>
                    false
                </replaceTargetName>
            </MaterialConnectToTargetsRequest>

        :param List[MaterialTarget] target_materials:
        :param bool use_copy_method:
        :param bool replace_target_name:
        :return:
        """
        e = self.create_request_element('Material', 'ConnectToTargets')
        material_names_parent = Et.SubElement(e, 'materialNames')
        target_names_parent = Et.SubElement(e, 'targetNames')

        # -- Add source materials and their corresponding targets
        for target in target_materials:
            material_node = Et.SubElement(material_names_parent, 'string')
            material_node.text = target.visible_variant
            target_node = Et.SubElement(target_names_parent, 'string')
            target_node.text = target.name

        # -- Add additional parameters
        for tag, value in [('useCopyMethod', use_copy_method), ('replaceTargetName', replace_target_name)]:
            param_node = Et.SubElement(e, tag)
            param_node.text = 'true' if value else 'false'

        self.request = e

    def request_to_string(self):
        return Et.tostring(self.request,
                           xml_declaration=True,
                           encoding="utf-8",
                           pretty_print=True).decode('utf-8')


class ConfigPlmXml:
    def __init__(self, plm_xml: PlmXml, config: str):
        """ Parses a configuration String against an initialized PlmXml instance and returns the
            product instances and looks that need their visibility or source looks changed.

        :param PlmXml plm_xml: PlmXml instance holding info about look library and product instances
        :param str config: Configuration String
        """
        self.plm_xml = plm_xml
        self.config = config
        self._parse_plmxml_against_config()

    def update_config(self, config: str):
        self.config = config
        self._parse_plmxml_against_config()

    def _match(self, pr_tags) -> bool:
        """ Match a PR Tag against the current configuration string """
        m = re.match(pr_tags_to_reg_ex(pr_tags), self.config, flags=re.IGNORECASE)

        if m:
            return True

        return False

    def _parse_plmxml_against_config(self):
        # -- Set Visibility of Geometry
        for _id, p in self.plm_xml.product_instances.items():
            if not p.pr_tags:
                continue

            # Match PR TAGS against configuration
            if self._match(p.pr_tags):
                p.visible = True
            else:
                p.visible = False

            if self.plm_xml.debug:
                LOGGER.debug(f'Switching Product Instance {p.name[:40]:40} - {p.visible:>5}')

        # -- Reset visible variants
        for target in self.plm_xml.look_lib.materials.values():
            target.visible_variant = None

        # -- Assign Source to Target materials
        for target, variant in self.plm_xml.look_lib.iterate_materials():
            if not variant.pr_tags:
                continue

            if self._match(variant.pr_tags):
                target.visible_variant = variant.name

                if self.plm_xml.debug:
                    LOGGER.debug(f'Switching Material {target.name[:40]:40} -> {variant.name}')

        request = self.create_material_update_request()

        # -- Print result
        LOGGER.info(f'Found '
                    f'{len([t for t, v in self.plm_xml.look_lib.iterate_materials() if v.name == t.visible_variant])} '
                    f'Materials to update and '
                    f'{len([_id for _id, p in self.plm_xml.product_instances.items() if p.pr_tags])} objects to '
                    f'update their visibility.')

        not_updated = [t.name for t in self.plm_xml.look_lib.materials.values() if not t.visible_variant]
        LOGGER.info(f'The following {len(not_updated)} Materials did not match the config and will not be updated:\n'
                    f'{"; ".join(not_updated)}')

        LOGGER.debug('Material Update Request:\n%s', request.request_to_string())

    def create_material_update_request(self) -> AsConnectorRequest:
        request = AsConnectorRequest()
        targets = [t for t, v in self.plm_xml.look_lib.iterate_materials() if v.name == t.visible_variant]
        request.create_material_connect_request(targets)
        return request


if __name__ == '__main__':
    setup_logging(Queue())
    LOGGER = init_logging(DEV_LOGGER_NAME)

    plm_xml = PlmXml(plm_xml_file)
    config = ConfigPlmXml(plm_xml, example_pr_string)
