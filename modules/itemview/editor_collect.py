from bisect import bisect_left
from typing import List, Union

from PySide2.QtCore import QModelIndex, QObject, QUuid, Signal

from modules.itemview.item import KnechtItem
from modules.itemview.model import KnechtModel
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.knecht_camera import KnechtImageCameraInfo
from modules.knecht_objects import KnechtVariantList
from modules.language import get_translation
from modules.log import init_logging
from modules.settings import KnechtSettings

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class KnechtCollectVariants(QObject):
    """ Helper class for KnechtEditor to collect variants from the current model """
    reset_missing = Signal()
    recursion_limit = 3

    def __init__(self, view):
        """ Collects variants, so basically Name and Value fields of model items.

        :param modules.itemview.treeview.KnechtTreeView view: The Tree View to collect variants from
        """
        super(KnechtCollectVariants, self).__init__()
        self.view = view
        self.recursion_depth = 0

    def collect_current_index(self, collect_reset: bool=True) -> KnechtVariantList:
        """ Collect variants from the current model index """
        index, __ = self.view.editor.get_current_selection()
        return self.collect_index(index, collect_reset)

    def collect_index(self, index: QModelIndex, collect_reset: bool=True) -> KnechtVariantList:
        """ Collect variants from the given model index """
        self.recursion_depth = 0
        src_model = self.view.model().sourceModel()

        if not index or not index.isValid():
            return KnechtVariantList()

        return self._collect(index, src_model, collect_reset)

    def _collect(self, index: QModelIndex, src_model: KnechtModel, collect_reset: bool=True
                 ) -> KnechtVariantList:
        variants = KnechtVariantList()
        current_item = src_model.get_item(index)
        reset_found = False

        if not current_item:
            return variants

        if KnechtSettings.dg['reset'] and collect_reset and current_item.userType != Kg.camera_item:
            reset_found = self._collect_reset_preset(variants, src_model)

        if current_item.userType == Kg.reference:
            # Current item is reference, use referenced item instead
            ref_id = current_item.reference
            current_item = src_model.id_mgr.get_preset_from_id(ref_id)

            if not current_item:
                return variants

        if current_item.userType in (Kg.variant, Kg.output_item):
            self._add_variant(current_item, variants, src_model)
            return variants

        variants.preset_name = current_item.data(Kg.NAME)
        variants.preset_id = current_item.preset_id
        self._collect_preset_variants(current_item, variants, src_model)

        if not reset_found and variants.plm_xml_path is None:
            self.reset_missing.emit()

        return variants

    def _collect_preset_variants(self, preset_item: KnechtItem, variants_ls: KnechtVariantList,
                                 src_model: KnechtModel) -> None:
        self.recursion_depth = 0
        self._collect_preset_variants_recursive(preset_item, variants_ls, src_model)

    def _collect_reset_preset(self, variants_ls: KnechtVariantList, src_model: KnechtModel):
        reset_presets = list()

        for item in src_model.id_mgr.iterate_presets():
            if item.data(Kg.TYPE) == 'reset':
                reset_presets.append(item)

        if not reset_presets:
            return False

        for reset_preset in reset_presets:
            self._collect_preset_variants(reset_preset, variants_ls, src_model)

        return True

    def _collect_preset_variants_recursive(self, preset_item: KnechtItem, variants_ls: KnechtVariantList,
                                           src_model: KnechtModel) -> None:
        if self.recursion_depth > self.recursion_limit:
            LOGGER.warning('Recursion limit reached while collecting references! Aborting further collections!')
            return

        ordered_child_ls = self._order_children(preset_item)

        if preset_item.userType == Kg.camera_item:
            self._add_camera_variants(preset_item, variants_ls, src_model)
            return

        for child in ordered_child_ls:
            self._add_variant(child, variants_ls, src_model)

            if child.userType == Kg.reference:
                ref_preset = self._collect_single_reference(child, src_model)

                if ref_preset.userType in (Kg.output_item, Kg.plmxml_item):
                    self._add_variant(ref_preset, variants_ls, src_model)
                    continue

                if ref_preset.userType == Kg.camera_item:
                    self._add_camera_variants(ref_preset, variants_ls, src_model)
                    continue

                if ref_preset:
                    self.recursion_depth += 1
                    self._collect_preset_variants(ref_preset, variants_ls, src_model)

    @staticmethod
    def _add_variant(item: KnechtItem, variants: KnechtVariantList, src_model: KnechtModel) -> None:
        if item.userType == Kg.variant:
            index = src_model.get_index_from_item(item)
            variants.add(index, item.data(Kg.NAME), item.data(Kg.VALUE), item.data(Kg.TYPE))
        elif item.userType == Kg.output_item:
            variants.output_path = item.data(Kg.VALUE)
            LOGGER.debug('Collected output path: %s', item.data(Kg.VALUE))
        elif item.userType == Kg.plmxml_item:
            variants.plm_xml_path = item.data(Kg.VALUE)
            LOGGER.debug('Collected PlmXml path: %s', item.data(Kg.VALUE))

    @staticmethod
    def _add_camera_variants(item: KnechtItem, variants: KnechtVariantList, src_model: KnechtModel) -> None:
        """ Convert Camera Preset items to camera command variants """
        for child in item.iter_children():
            camera_tag, camera_value = child.data(Kg.NAME), child.data(Kg.VALUE)

            if camera_tag in KnechtImageCameraInfo.rtt_camera_cmds:
                index = src_model.get_index_from_item(child)
                camera_cmd = KnechtImageCameraInfo.rtt_camera_cmds.get(camera_tag)
                camera_value = camera_value.replace(' ', '')

                try:
                    camera_cmd = camera_cmd.format(*camera_value.split(','))
                except Exception as e:
                    LOGGER.warning('Camera Info Tag Value does not match %s\n%s', camera_value, e)

                variants.add(index, camera_tag, camera_cmd, 'command')

                LOGGER.debug('Collecting Camera Command %s: %s', camera_tag, camera_cmd)

    @classmethod
    def _order_children(cls, preset_item: KnechtItem) -> List[KnechtItem]:
        """ The children list of an item corresponds to the source indices which
            do not necessarily reflect the item order by order column.
            We create a list ordered by the order column value of each child.
        """
        return cls.order_items_by_order_column(preset_item.iter_children())

    @staticmethod
    def order_items_by_order_column(items: List[KnechtItem]):
        item_order_ls, item_ls = list(), list()

        for item in items:
            order = int(item.data(Kg.ORDER))
            item_order_ls.append(order)

            insert_idx = bisect_left(sorted(item_order_ls), order)
            item_ls.insert(insert_idx, item)

        return item_ls

    @staticmethod
    def _collect_single_reference(item, src_model) -> Union[KnechtItem, None]:
        ref_id: QUuid = item.reference

        if ref_id:
            return src_model.id_mgr.get_preset_from_id(ref_id)
        else:
            return KnechtItem()
