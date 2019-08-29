from pathlib import Path
from threading import Thread
from typing import Union, List

from PIL import Image
from PySide2.QtCore import QObject, Signal
import numpy as np
from imageio import imread, imwrite

from modules.gui.widgets.path_util import path_exists
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class KnechtImage(QObject):
    supported_image_types = ['.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.exr', '.hdr']

    conversion_result = Signal(str)

    def __init__(self, parent=None):
        super(KnechtImage, self).__init__(parent)

    def convert_file(self, img_file: Path, output_dir: Path=Path('.'),
                     output_format: str='.png', move_converted: bool=False) -> bool:
        if not path_exists(img_file) or not path_exists(output_dir):
            return False

        self._start_img_thread([img_file, ], output_dir, output_format, move_converted)
        return True

    def convert_directory(self, img_dir: Path, output_dir: Path=Path('.'),
                          output_format: str='.png', move_converted: bool=False) -> bool:
        if not path_exists(img_dir) or not path_exists(output_dir):
            return False

        img_list = list()
        for file in img_dir.glob('*.*'):
            if file.suffix.casefold() in self.supported_image_types:
                img_list.append(file)

        if not img_list:
            return False

        self._start_img_thread(img_list, output_dir, output_format, move_converted)
        return True

    def _start_img_thread(self, img_list: List[Path], output_dir: Path,
                          output_format: str, move_converted: bool):
        img_thread = ConversionThread(img_list, self.conversion_result, output_dir, output_format, move_converted)
        img_thread.start()

    @staticmethod
    def open_with_imageio(file: Path) -> Union[None, np.array]:
        """ Open image files with imageio and convert to 8bit """
        try:
            LOGGER.info('Loading image file with imageio. %s', file.name)
            img = imread(file.as_posix())
        except Exception as e:
            LOGGER.error(e)
            return None

        # Convert none 8bit depth images
        if img.dtype == np.float32:
            # Convert 32bit float images to 8bit integer
            img = np.uint8(img * 255)
        elif img.dtype == np.uint16:
            # Convert 16bit integer[0 - 65535] to 8bit integer [0-255]
            img = np.uint8(img / 256)

        return img


class ConversionThread(Thread):
    unconverted_dir_name = 'non_converted_images'

    def __init__(self, img_list: List[Path], result_signal: Signal, output_dir: Path=Path('.'),
                 output_format: str='.png', move_converted: bool=False):
        super(ConversionThread, self).__init__()

        self.img_list = img_list
        self.output_dir = output_dir
        self.output_format = output_format
        self.move_converted = move_converted

        self.result_signal = result_signal

    def run(self):
        result = str()

        for img_file in self.img_list:
            if self.output_dir == Path('.'):
                self.output_dir = img_file.parent

            if not path_exists(self.output_dir):
                try:
                    self.output_dir.mkdir(parents=True)
                except Exception as e:
                    result += _('Konnte Ausgabe Verzeichnis nicht erstellen: {}').format(f'{e}\n')
                    break

            # Open and convert image
            try:
                img = KnechtImage.open_with_imageio(img_file)
            except Exception as e:
                result += _('Konnte Bilddatei {} nicht konvertieren: {}').format(img_file.name, f'{e}\n')
                continue

            # Write image to file
            try:
                img_out = self.output_dir / Path(img_file.stem).with_suffix(self.output_format)
                imwrite(img_out, img)
                result += _('Bilddatei erstellt: {}').format(f'{img_out.name}\n')
            except Exception as e:
                result += _('Konnte Bilddatei {} nicht erstellen: {}').format(img_file.name, f'{e}\n')
                continue

            # Move source files
            if not self.move_converted or img_file.suffix == self.output_format:
                continue

            # Create un-converted directory
            move_dir = self.output_dir.parent / self.unconverted_dir_name
            if not path_exists(move_dir):
                move_dir.mkdir(parents=True)

            # Move the file to un-converted directory
            try:
                img_file.replace(move_dir / img_file.name)
                LOGGER.debug('Moving un-converted image file: %s', img_file.name)
            except FileNotFoundError or FileExistsError:
                result += _('Konnte unkonvertierte Bilddatei nicht verschieben: {}').format(
                    f'{img_file.name}')
                pass

        self.result_signal.emit(result)


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
                       }

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
        }

    # Example dictonary for item creation
    camera_example_info = {
        'Software'                       : '3DEXCITE DELTAGEN 2017.1', 'rtt_Camera_FOV': '38.8801',
        'rtt_Camera_FocalLength'         : '34', 'rtt_Camera_Projection': '1', 'rtt_Camera_EyeSeparation': '77.44',
        'rtt_Camera_ConvergenceDistance' : '34', 'rtt_Camera_PreScale': '1', 'rtt_Camera_Overscan': '1',
        'rtt_Camera_HorizontalFilmOffset': '0', 'rtt_Camera_VerticalFilmOffset': '0',
        'rtt_Camera_HorizontalSensorSize': '36', 'rtt_Camera_VerticalSensorSize': '24', 'rtt_Camera_FilmFit': '2',
        'rtt_Camera_RenderOutputWidth'   : '2880', 'rtt_Camera_RenderOutputHeight': '1620',
        'rtt_Camera_Position'            : '1658.65, 483.29, 866.389',
        'rtt_Camera_Orientation'         : '0.261426, 0.586788, 0.766379, 2.48355',
        'rtt_BackgroundColor_RGBA'       : '1, 1, 1, 1', 'rtt_width': '1920', 'rtt_height': '1080',
        'rtt_antiAliasQuality'           : '8',
        'rtt_FileName'                   : 'Some_File.csb'
        }

    def __init__(self, file: Union[str, Path]):
        self.file = file
        self.file_is_valid = False
        self.info_is_valid = False

        self._camera_info = dict()

    def read_image(self) -> bool:
        if path_exists(self.file):
            self.file_is_valid = True
        else:
            return False

        # Open Image with Pillow
        try:
            with open(self.file, 'rb') as fp:
                im = Image.open(fp)
        except Exception as e:
            LOGGER.error(e)
            return False

        # Read through image info dict for required camera tags
        for k, v in im.info.items():
            for tag in self.rtt_camera_tags:
                if k.startswith(tag):
                    self._camera_info[k] = v

        if not im.info or not self._camera_info:
            return False
        else:
            # Test if all required camera command keys are inside camera info
            if self._camera_info.keys().isdisjoint(self.rtt_camera_cmds.keys()):
                return False
            self.info_is_valid = True

        # Convert Camera Orientation
        self._convert_orientation()

        return True

    def _convert_orientation(self):
        """ rtt_Camera_Orientation is stored X Y Z ANGLE rotation axis in radians + rotation angle in radians
            socket command wants X Y Z in radians but angle in degrees ...
        """
        v = self._camera_info.get('rtt_Camera_Orientation') or ''
        values = v.replace(' ', '').split(',')

        if not len(values) == 4:
            return

        x, y, z, radian_angle = values
        degree_angle = np.math.degrees(float(radian_angle))

        self._camera_info['rtt_Camera_Orientation'] = f'{x}, {y}, {z}, {degree_angle}'

    def camera_info(self):
        return self._camera_info

    def is_valid(self):
        if self.file_is_valid and self.info_is_valid and self._camera_info:
            return True
        return False
