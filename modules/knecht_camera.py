from pathlib import Path
from typing import Union

import numpy as np
from PySide2.QtCore import Qt

from modules.gui.widgets.path_util import path_exists
from modules.itemview.model import KnechtModel
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.knecht_image import OpenImageUtil
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class KnechtImageCameraInfo:
    """ Read Camera information from PNG files written from 3DS DeltaGen """
    # Define which "tEXt" chunks to read from DeltaGen PNG files
    # will test wildcard style with startswith(tag)
    rtt_camera_tags = {'rtt_width', 'rtt_height',   # most likely refers to window resolution
                       'rtt_Camera',                # read all tags starting with rtt_Camera
                       'Software',                  # contains version information
                       'rtt_BackgroundColor_RGBA',  # viewer background color
                       'rtt_antiAliasQuality',      # AA Sampling value 0-9
                       'rtt_FileName',              # Scene file name
                       'knecht',                    # Custom RenderKnecht data
                       }
    
    # Default values, we will warn if those differ in the camera info because they can not
    # be send to DeltaGen via external commands
    rtt_camera_defaults = {'rtt_Camera_HorizontalFilmOffset': '0', 'rtt_Camera_VerticalFilmOffset': '0',
                           'rtt_Camera_PreScale': '1', 'rtt_Camera_Overscan': '1'}

    # Define which camera info tag belongs to which CAMERA socket command
    rtt_camera_cmds = {
        'rtt_Camera_FOV': 'FOV CAMERA {0}',
        'rtt_Camera_Position': 'POS CAMERA {0} {1} {2}',
        'rtt_Camera_Orientation': 'ORIENT CAMERA {0} {1} {2} {3}',
        'knecht_clip_near': 'CLIPPLANE_NEAR CAMERA {0}',
        'knecht_clip_far': 'CLIPPLANE_FAR CAMERA {0}',
        }

    # Define item descriptions for certain camera tags
    rtt_camera_desc = {
        'rtt_Camera_FOV': _('DeltaGen Kamera Sichtfeld: Angle'),
        'rtt_Camera_Position': _('DeltaGen Kamera Position: X, Y, Z'),
        'rtt_Camera_Orientation': _('DeltaGen Kamera Orientierung: Rotation Vector X, Y, Z, Angle'),
        'rtt_BackgroundColor_RGBA': _('Viewer Hintergrund Farbe: R, G, B, A'),
        'rtt_width': _('Viewer Breite in Px'),
        'rtt_height': _('Viewer Höhe in Px'),
        'rtt_Camera_RenderOutputWidth': _('Ausgabe Breite in Px'),
        'rtt_Camera_RenderOutputHeight': _('Ausgabe Höhe in Px'),
        'rtt_antiAliasQuality': 'Anti Aliasing Sampling Factor',
        'knecht_clip_near': 'Near Clipping Plane', 'knecht_clip_far': 'Far Clipping Plane',
        }

    # Example dictonary for item creation
    camera_example_info = {
        'Software'                       : '3DEXCITE DELTAGEN 2017.1', 'rtt_Camera_FOV': '38.8801',
        'rtt_Camera_FocalLength'         : '34', 'rtt_Camera_Projection': '1', 'rtt_Camera_EyeSeparation': '77.44',
        'rtt_Camera_ConvergenceDistance' : '34', 'rtt_Camera_PreScale': '1', 'rtt_Camera_Overscan': '1',
        'rtt_Camera_HorizontalFilmOffset': '0', 'rtt_Camera_VerticalFilmOffset': '0',
        'rtt_Camera_HorizontalSensorSize': '36', 'rtt_Camera_VerticalSensorSize': '24', 'rtt_Camera_FilmFit': '2',
        'rtt_Camera_RenderOutputWidth'   : '2880', 'rtt_Camera_RenderOutputHeight': '1620',
        'rtt_Camera_Position'            : '-221.522, -143.877, 88.475',
        'rtt_Camera_Orientation'         : '0.734806, -0.397707, -0.549444, 89.13848193527295',
        'rtt_BackgroundColor_RGBA'       : '1, 1, 1, 1', 'rtt_width': '1920', 'rtt_height': '1080',
        'rtt_antiAliasQuality'           : '8',
        'rtt_FileName'                   : 'Some_File.csb',
        'knecht_clip_near': '100.0', 'knecht_clip_far': '10000.0',
        }

    def __init__(self, file: Union[str, Path]):
        self.file = file
        self.file_is_valid = False
        self.info_is_valid = False

        self.camera_warning = ''

        self.camera_info = dict()

    def read_image(self) -> bool:
        if path_exists(self.file):
            self.file_is_valid = True
        else:
            return False

        # Get image meta data with OpenImageIO
        try:
            img_meta = OpenImageUtil.read_img_metadata(self.file)
        except Exception as e:
            LOGGER.error(e)
            return False

        # Read through image info dict for required camera tags
        for k, v in img_meta.items():
            for tag in self.rtt_camera_tags:
                if k.startswith(tag):
                    self.camera_info[k] = v

        if not img_meta or not self.camera_info:
            return False
        else:
            # Test if all required camera command keys are inside camera info
            if self.camera_info.keys().isdisjoint(self.rtt_camera_cmds.keys()):
                return False
            self.info_is_valid = True

        # Convert Camera Orientation
        self._convert_orientation()

        return True

    def _convert_orientation(self):
        """ rtt_Camera_Orientation is stored X Y Z ANGLE rotation axis in radians + rotation angle in radians
            socket command wants X Y Z in radians but angle in degrees ...
        """
        v = self.camera_info.get('rtt_Camera_Orientation') or ''
        values = v.replace(' ', '').split(',')

        if not len(values) == 4:
            return

        x, y, z, radian_angle = values
        degree_angle = np.math.degrees(float(radian_angle))

        self.camera_info['rtt_Camera_Orientation'] = f'{x}, {y}, {z}, {degree_angle}'

    def is_valid(self):
        if self.file_is_valid and self.info_is_valid and self.camera_info:
            return True
        return False

    @classmethod
    def validate_camera_items(cls, view):
        """
        Compare camera_item values with default values and warn if
        there are values that can not be send to DeltaGen

        :param modules.itemview.tree_view.KnechtTreeView view:
        :return:
        """
        if view.is_render_view:
            return

        close_btn = ('[X]', None)
        src_model: KnechtModel = view.model().sourceModel()
        prx_indices_to_select = list()
        highlight_items = []

        # Iterate Camera Items
        for index in view.editor.match.indices(Kg.xml_tag_by_user_type[Kg.camera_item], Kg.TYPE):
            src_index = view.model().mapToSource(index)
            item_valid, warn_msg = True, ''
            name = index.siblingAtColumn(Kg.NAME).data(Qt.DisplayRole)

            for child_idx, child in view.editor.iterator.iterate_view(src_index):
                tag, value = child.data(Kg.NAME), child.data(Kg.VALUE)
                default_value = cls.rtt_camera_defaults.get(tag)

                if default_value is not None and value is not None:
                    if value != default_value:
                        highlight_items.append(child)
                        prx_indices_to_select.append(child_idx)
                        warn_msg += _('{}: {}<br />').format(tag, value)
                        item_valid = False

            if not item_valid:
                msg = _('<b>Achtung!</b><br /><i>{}</i><br />'
                        'Es wurden Kameraeinstellungen gefunden die nicht an DeltaGen '
                        'gesendet werden können:<br />{}').format(name, warn_msg)
                view.info_overlay.display_confirm(msg, (close_btn,))

        # Point user to problematic values
        if highlight_items:
            src_model.style_recursive_items(highlight_items)
            view.editor.selection.clear_and_select_src_index_ls(prx_indices_to_select)
