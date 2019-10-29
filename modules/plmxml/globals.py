PLM_XML_NAMESPACE = '{http://www.plmxml.org/Schemas/PLMXMLSchema}'
AS_CONNECTOR_IP = '127.0.0.1'
AS_CONNECTOR_PORT = 1234
AS_CONNECTOR_API_URL = 'v2'

# Xpath for <PLMXML>/<ProductDef>/<InstanceGraph>/<ProductInstance>
PRODUCT_INSTANCE_XPATH = f'{PLM_XML_NAMESPACE}ProductDef/' \
                         f'{PLM_XML_NAMESPACE}InstanceGraph/' \
                         f'{PLM_XML_NAMESPACE}ProductInstance'
PRODUCT_INSTANCE_TAGS = {
    'part_ref': 'partRef', 'id': 'id', 'name': 'name', }

# Xpath for child node <ProductInstance>/<UserData>/<UserValue>
USER_DATA_XPATH = f"{PLM_XML_NAMESPACE}UserData/" \
                  f"{PLM_XML_NAMESPACE}UserValue"

LOOK_LIBRARY_INSTANCE_NAME = 'LookLibrary'
