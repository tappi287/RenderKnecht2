from typing import Union

from lxml import etree as Et

from modules.knecht_objects import KnechtVariantList
from modules.language import get_translation
from modules.log import init_logging
from modules.plmxml.globals import PlmXmlGlobals as Pg

LOGGER = init_logging(__name__)


# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


def create_pr_string_from_variants(variants_ls: KnechtVariantList) -> str:
    pr_conf = ''

    for variant in variants_ls.variants:
        pr_conf += f'+{variant.name}'

    return pr_conf


def _split_not_pr_tag(t):
    """ Split incoming PR-Tag Part ABC!DEF or !DEF or DEF
        => ABC!DEF -> (?=.*\bABC\b)(?!.*\bDEF\b)
        => !DEF -> (?!.*\bDEF\b)
        => DEF -> (?=.*\bDEF\b)

    :param t: input PR-Tag part
    :return: Reg-Ex pattern
    """
    if '!' in t and t[0] != '!':
        # Case were NOT operator -is not- separated by +
        # t = ABC!DEF
        n_ex = f'(?=.*\\b{t.split("!")[0]}\\b)'
        for n in t.split('!')[1:]:
            n_ex += f'(?!.*\\b{n}\\b)'
    elif t[0] == '!':
        # Case were NOT operator -is- separated by +
        # ABC+!DEF
        # t = !DEF
        n_ex = f'(?!.*\\b{t[1:]}\\b)'
    else:
        # Case with -no- NOT operator
        # t = DEF
        n_ex = f'(?=.*\\b{t}\\b)'

    return n_ex


def pr_tags_to_reg_ex(pr_tags: Union[None, str]) -> str:
    """ Convert PR_TAGS to RegEx pattern that can be matched against a complete configuration string.

        Example:
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
                    s_ex += f'{_split_not_pr_tag(s)}|'
                s_ex = f'({s_ex[:-1]})'
            elif w:
                r_ex = _split_not_pr_tag(w)

            tag_pattern += r_ex + s_ex

        if tag_pattern:
            # Combine all <tag> as OR combination
            # each matching against the whole string ^<tag_pattern>.*$
            #
            pattern += f'^{tag_pattern}.*$|'

    # Remove trailing OR '|'
    #
    return pattern[:-1]


def create_attribute_child_tag(parent_element: Et._Element, tag: str, value: str):
    if value:
        e = Et.SubElement(parent_element, tag)
        e.text = value


def create_user_attributes_elements_from_dict(parent, attrib_dict):
    """

    :param Et._Element parent:
    :param dict attrib_dict:
    :return:
    """
    ua = Et.SubElement(parent, 'UserAttributes')

    for key, value in attrib_dict.items():
        a = Et.SubElement(ua, 'UserAttribute')
        k = Et.SubElement(a, 'Key')
        k.text = key
        v = Et.SubElement(a, 'Value')
        v.text = value


def find_text_attribute(child, attr_name) -> str:
    found_attribute = child.find(f'{Pg.AS_CONNECTOR_XMLNS}{attr_name}')
    if found_attribute is not None:
        return found_attribute.text
    else:
        return ""


def find_user_attributes_in_element(child) -> dict:
    """ Helper to find the UserAttributeArray """
    user_attribute_dict = dict()
    user_attributes = child.find(f'{Pg.AS_CONNECTOR_XMLNS}UserAttributes')

    if user_attributes is None:
        return user_attribute_dict

    for ua in user_attributes:
        ua_key = ua.find(f'{Pg.AS_CONNECTOR_XMLNS}Key')
        ua_value = ua.find(f'{Pg.AS_CONNECTOR_XMLNS}Value')

        if ua_key is not None and ua_value is not None:
            user_attribute_dict[ua_key.text] = ua_value.text

    return user_attribute_dict
