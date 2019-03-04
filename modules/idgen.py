from typing import Union

from PySide2.QtCore import QUuid

from modules.itemview.model_globals import KnechtModelGlobals as Kg


class KnechtUuidGenerator:
    """ Creates and converts QUuid's """
    @staticmethod
    def is_quuid(_id=None) -> bool:
        if isinstance(_id, QUuid):
            return True
        return False

    @staticmethod
    def create_id(_id: Union[str, QUuid, None]=None) -> QUuid:
        if is_valid_uuid(_id):
            return _id

        return create_uuid()

    @staticmethod
    def convert_column_data_id(_id: list) -> list:
        """
            Converts old Integer Id's to uuid's
            Accepts a column data list
        """
        if not isinstance(_id, list):
            return _id

        # Convert Reference Id
        if len(_id) > Kg.REF:
            if _id[Kg.REF].isdigit():
                _id[Kg.REF] = create_uuid()
                return _id
        # Convert Item Id
        if len(_id) > Kg.ID:
            if _id[Kg.ID].isdigit():
                _id[Kg.ID] = create_uuid()
                return _id

        return _id

    @staticmethod
    def convert_id(_id: str) -> Union[QUuid, str]:
        """
            Converts old integer Id's to uuid's
            Accepts a single string value
        """
        if _id.isdigit():
            return create_uuid()

        return _id


def is_valid_uuid(_id: Union[str, QUuid]) -> bool:
    if isinstance(_id, QUuid):
        _id = _id.toByteArray()
    return not QUuid(_id).isNull()


def create_uuid() -> QUuid:
    # noinspection PyArgumentList
    return QUuid.createUuid()
