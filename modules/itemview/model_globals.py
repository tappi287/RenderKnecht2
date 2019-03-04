from modules.language import get_translation

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class KnechtModelGlobals:
    # --- Column identifiers ---
    DESC = 6    # description
    ID = 5      # Unique Item ID
    REF = 4     # referenced ID
    TYPE = 3    # type, see column types
    VALUE = 2   # value
    NAME = 1    # name
    ORDER = 0   # order

    column_keys = ('order', 'name', 'value', 'type', 'reference', 'id', 'description')
    column_range = range(0, 7)
    column_count = 7
    column_desc = [_('Order'), _('Name'), _('Wert'), _('Typ'), _('Referenz'), _('Id'), _('Beschreibung')]
    column_type_keys = ('preset', 'trim_setup', 'options', 'package', 'reset', 'viewset', 'fakom_setup', 'fakom_option')

    TYPE_MAPPING = dict(
        trim_setup='preset',
        fakom_setup='preset', fakom_option='preset',
        options='preset',
        package='preset',
        viewset='preset', viewset_mask='preset',
        reset='preset',
        render_preset='render_preset',
        sampling='render_setting', file_extension='render_setting', resolution='render_setting',
        separator='separator', sub_separator='sub_separator', seperator='separator', sub_seperator='Sub_separator'
        )

    # White Filter to apply on quick filtering
    QUICK_VIEW_FILTER = ['preset', 'separator', 'render_preset']

    # Column to decorate with icon
    style_column = 0

    # XML DOM / hierarchy tags
    xml_dom_tags = dict(
        root='renderknecht_varianten',
        level_1='variant_presets',
        level_2='preset',
        settings='renderknecht_settings',
        origin='origin'
        )

    xml_tag_user_type = {
        'preset': 1000, 'variant': 1001, 'reference': 1002, 'render_preset': 1003,
        'render_setting': 1004, 'separator': 1005, 'seperator': 1005, 'sub_seperator': 1006, 'sub_separator': 1006
        }

    xml_tag_by_user_type = dict()
    for k, v in xml_tag_user_type.items():
        xml_tag_by_user_type[v] = k

    # Default, read from source presets, do not search for references in them
    # if they are in source widget(for performance)
    column_type_default_keys = ('trim_setup', 'options', 'package', 'reset', 'viewset', 'fakom_setup', 'fakom_option')

    # --- Item userType ---
    type_num, type_keys = dict(), dict()

    for idx, desc in enumerate(
            ['preset', 'variant', 'reference', 'render_preset',
             'render_setting', 'separator', 'sub_separator', 'checkable']):
        type_keys[1000 + idx] = desc

    # Qt UserTypes will be in 1000s
    preset = 1000
    variant = 1001
    reference = 1002
    render_preset = 1003
    render_setting = 1004
    separator = 1005
    sub_separator = 1006
    checkable = 1007
