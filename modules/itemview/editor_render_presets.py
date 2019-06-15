from typing import Generator, Tuple, Any
from pathlib import Path

from PySide2.QtCore import QModelIndex, QUuid

from modules.itemview.model import KnechtModel
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.knecht_objects import KnechtRenderPreset, KnechtVariantList
from modules.log import init_logging

LOGGER = init_logging(__name__)


class KnechtEditorRenderPresets:
    """
        View Editor helper class for render presets
    """
    def __init__(self, editor):
        self.editor = editor

    @property
    def view(self):
        return self.editor.view

    def clear_view_render_presets(self, view):
        """ Remove render presets that link to provided destroyed view """
        if not self.view.model() or not self.view.is_render_view:
            return

        self.editor.view.model().clear_filter()

        indices_to_remove = list()

        # Iterate all render presets
        for src_index, item in self.view.editor.iterator.iterate_view():
            if item.origin == view:
                LOGGER.debug('Removing Render Preset linking to TreeView about to be destroyed: %s', item.data(Kg.NAME))
                indices_to_remove.append(src_index)

        # Select items to remove
        self.editor.selection.clear_and_select_src_index_ls(indices_to_remove)
        # Remove selected items
        self.editor.remove_rows()

        # Make changes undoable - avoid access to destroyed objects
        LOGGER.debug('Clearing renderTree undo stack.')
        self.view.undo_stack.clear()

        # Set undo stack active of view that has been cleared
        view.undo_stack.setActive(True)

    @staticmethod
    def _collect_referenced_preset_variants(reference: QUuid, view_origin, collect_reset=True) -> KnechtVariantList:
        """ Generic variants collection from a referenced preset from the originating view

        :param QUuid reference: Unique Id of the preset to collect
        :param modules.itemview.tree_view.KnechtTreeView view_origin: TreeView the render presets originates from
        :return:
        """
        origin_model: KnechtModel = view_origin.model().sourceModel()

        preset_item = origin_model.id_mgr.get_preset_from_id(reference)

        if preset_item and preset_item.data(Kg.TYPE) == 'viewset':
            collect_reset = False

        preset_index = origin_model.get_index_from_item(preset_item)

        return view_origin.editor.collect.collect_index(preset_index, collect_reset=collect_reset)

    def _collect_references(self, render_preset_idx: QModelIndex, view_origin, collect_reset=True
                            ) -> Generator[Tuple[QModelIndex, Any], Tuple[bool, str, KnechtVariantList], None]:
        """ Collect referenced Presets inside render preset

        :param QModelIndex render_preset_idx: source model index of the current render preset
        :param modules.itemview.tree_view.KnechtTreeView view_origin: TreeView the render presets originates from
        """
        for src_index, item in self.view.editor.iterator.iterate_view(render_preset_idx):
            if not item.userType == Kg.reference:
                continue

            name = item.data(Kg.NAME)
            ref_id = item.reference
            is_viewset = False

            if not name:
                name = 'Render_Image_Name_Not_Set'

            variants = self._collect_referenced_preset_variants(ref_id, view_origin, collect_reset)

            if item.data(Kg.TYPE) == 'viewset':
                if not len(variants):
                    LOGGER.error('Could not collect Viewset variants for Render Preset Shot: %s!', name)
                    variants.add(QModelIndex(), 'Shot_Variant_Not_Set', 'Shot_Not_Set')
                    LOGGER.error('Adding Render Preset Shot dummy variant: Shot_Not_Set')

                name = variants.variants[0].value
                is_viewset = True

            yield is_viewset, name, variants

    def _collect_settings(self, render_preset_item, render_preset: KnechtRenderPreset):
        """ Collect Render Settings from Render Preset Item

        :param modules.itemview.item.KnechtItem render_preset_item: the KnechtItem to read settings from
        :param KnechtRenderPreset render_preset: the RenderPreset to update the settings of
        :return:
        """
        for child_item in render_preset_item.iter_children():
            if child_item.userType != Kg.render_setting:
                continue

            if child_item.data(Kg.TYPE) == 'sampling':
                render_preset.settings['sampling'] = int(child_item.data(Kg.VALUE))
            elif child_item.data(Kg.TYPE) == 'resolution':
                render_preset.settings['resolution'] = child_item.data(Kg.VALUE)
            elif child_item.data(Kg.TYPE) == 'file_extension':
                render_preset.settings['file_extension'] = child_item.data(Kg.VALUE)

    def collect_render_presets(self, collect_reset=True):
        """ Collect variants and settings of the render presets in the renderTree """
        if not self.view.model() or not self.view.is_render_view:
            return

        render_presets, result = list(), True

        for render_preset_index, item in self.view.editor.iterator.iterate_view():
            if not item.userType == Kg.render_preset:
                continue

            render_preset = KnechtRenderPreset(item.data(Kg.NAME))

            if not item.origin:
                # TODO: Handle errors when collecting render presets
                # Skip render presets that have no origin set
                LOGGER.debug('Render Preset Item %s has no origin set!', item.data(Kg.NAME))
                result = False
                continue

            # Collect referenced presets
            for is_viewset, name, variants in self._collect_references(render_preset_index, item.origin, collect_reset):
                if not variants:
                    result = False

                if is_viewset:
                    render_preset.add_shot(name, variants)
                else:
                    render_preset.add_image(name, variants)

            # Collect render settings
            self._collect_settings(item, render_preset)

            render_presets.append(render_preset)

        if result:
            return render_presets
