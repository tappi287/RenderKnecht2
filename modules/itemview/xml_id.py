from PySide2.QtCore import QUuid

from modules.idgen import KnechtUuidGenerator as Kid
from modules.itemview.item import KnechtItem
from modules.itemview.model_globals import KnechtModelGlobals


class KnechtXmlId:
    def __init__(self):
        self.item_ids = dict()
        self.str_ids = 0

    def update_preset_uuid(self, node, item):
        knecht_id = node.attrib.get('id')  # Knecht int Id or Uuid string
        if knecht_id:
            uuid = self.get_id(None, knecht_id)
        else:
            return

        self.store_id(uuid, knecht_id)
        item.preset_id = uuid
        item.setData(KnechtModelGlobals.ID, uuid)

    def update_reference_uuid(self, node, item: KnechtItem):
        ref_id = node.attrib.get('reference')  # Knecht int Reference Id or Uuid string
        if ref_id:
            ref_uuid = self.get_id(None, ref_id)
        else:
            return

        self.store_id(ref_uuid, ref_id)
        item.reference = ref_uuid
        item.setData(KnechtModelGlobals.REF, ref_uuid)

    def save_uuid(self, uuid: QUuid) -> str:
        """ Store a Quuid and return a integer id as string to minimize file save/load effort.
            This method should only be used on file saving!
        """
        uuid_str = uuid.toString()

        if uuid_str in self.item_ids:
            return self.item_ids[uuid_str]

        self.str_ids += 1
        str_id = str(self.str_ids)
        self.item_ids[uuid_str] = str_id
        return str_id

    def store_id(self, uuid, str_id) -> QUuid:
        if str_id not in self.item_ids:
            uuid = Kid.create_id(uuid)  # Returns QUuid from valid uuid string or new uuid if None or invalid str
            self.item_ids[str_id] = uuid
            return uuid

        return self.item_ids[str_id]

    def get_id(self, uuid, str_id) -> QUuid:
        stored_uuid = self.item_ids.get(str_id)

        if stored_uuid:
            return stored_uuid

        return Kid.create_id(uuid)  # Returns QUuid from valid uuid string or new uuid if None or invalid str
