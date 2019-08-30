from pathlib import Path
from threading import Thread
from typing import List, Union

import OpenImageIO as oiio
import numpy as np
from OpenImageIO import ImageBuf, ImageBufAlgo, ImageOutput, ImageSpec
from PySide2.QtCore import QObject, Signal

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
        if not img_file.suffix.casefold() in self.supported_image_types:
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
                img = OpenImageUtil.read_image(img_file)
            except Exception as e:
                result += _('Konnte Bilddatei {} nicht konvertieren: {}').format(img_file.name, f'{e}\n')
                continue

            # Write image to file
            try:
                img_out = self.output_dir / Path(img_file.stem).with_suffix(self.output_format)
                OpenImageUtil.write_image(img_out, img)
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


class OpenImageUtil:
    @classmethod
    def get_image_resolution(cls, img_file: Path) -> (int, int):
        img_input = cls._image_input(img_file)

        if img_input:
            res_x, res_y = img_input.spec().width, img_input.spec().height
            img_input.close()
            del img_input
            return res_x, res_y
        return 0, 0

    @classmethod
    def premultiply_image(cls, img_pixels: np.array) -> np.array:
        """ Premultiply a numpy image with itself """
        a = cls.np_to_imagebuf(img_pixels)
        ImageBufAlgo.premult(a, a)

        return a.get_pixels(a.spec().format, a.spec().roi_full)

    @staticmethod
    def get_numpy_oiio_img_format(np_array: np.ndarray) -> Union[oiio.BASETYPE]:
        """ Returns either float or 8 bit integer format"""
        img_format = oiio.FLOAT

        if np_array.dtype == np.uint8:
            img_format = oiio.UINT8
        elif np_array.dtype == np.uint16:
            img_format = oiio.UINT16

        return img_format

    @classmethod
    def convert_img_to_uint8(cls, img: np.ndarray) -> Union[None, np.ndarray]:
        """ Convert an image array to 8bit integer """
        img_format = cls.get_numpy_oiio_img_format(img)

        # Convert none 8bit depth images
        if img_format == oiio.FLOAT:
            # Convert 32bit float images to 8bit integer
            img = np.uint8(img * 255)
        elif img_format == oiio.UINT8:
            # Keep 8bit integers untouched
            pass
        elif img_format == oiio.UINT16:
            # Convert 16bit integer[0 - 65535] to 8bit integer [0-255]
            img = np.uint8(img / 256)

        return img

    @classmethod
    def np_to_imagebuf(cls, img_pixels: np.array):
        """ Load a numpy array 8/32bit to oiio ImageBuf """
        if len(img_pixels.shape) < 3:
            LOGGER.error('Can not create image with pixel data in this shape. Expecting 4 channels(RGBA).')
            return

        h, w, c = img_pixels.shape
        img_spec = ImageSpec(w, h, c, cls.get_numpy_oiio_img_format(img_pixels))

        img_buf = ImageBuf(img_spec)
        img_buf.set_pixels(img_spec.roi_full, img_pixels)

        return img_buf

    @classmethod
    def _image_input(cls, img_file: Path):
        """ CLOSE the returned object after usage! """
        img_input = oiio.ImageInput.open(img_file.as_posix())

        if img_input is None:
            LOGGER.error('Error reading image: %s', oiio.geterror())
            return
        return img_input

    @classmethod
    def read_image(cls, img_file: Path, format: str='') -> Union[np.ndarray, None]:
        img_input = cls._image_input(img_file)

        if not img_input:
            return None

        # Read out image data as numpy array
        img = img_input.read_image(format=format)
        img_input.close()

        return img

    @classmethod
    def write_image(cls, file: Path, pixels: np.array):
        output = ImageOutput.create(file.as_posix())
        if not output:
            LOGGER.error('Error creating oiio image output:\n%s', oiio.geterror())
            return

        if len(pixels.shape) < 3:
            LOGGER.error('Can not create image with Pixel data in this shape. Expecting 3 or 4 channels(RGB, RGBA).')
            return

        h, w, c = pixels.shape
        spec = ImageSpec(w, h, c, cls.get_numpy_oiio_img_format(pixels))

        result = output.open(file.as_posix(), spec)
        if result:
            try:
                output.write_image(pixels)
            except Exception as e:
                LOGGER.error('Could not write Image: %s', e)
        else:
            LOGGER.error('Could not open image file for writing: %s: %s', file.name, output.geterror())

        output.close()

    @classmethod
    def read_img_metadata(cls, img_file: Path) -> dict:
        img_buf = ImageBuf(img_file.as_posix())
        img_dict = dict()

        if not img_buf:
            LOGGER.error(oiio.geterror())
            return img_dict

        for param in img_buf.spec().extra_attribs:
            img_dict[param.name] = param.value

        cls.close_img_buf(img_buf, img_file)

        return img_dict

    @staticmethod
    def close_img_buf(img_buf, img_file: Union[Path, None]=None):
        try:
            img_buf.clear()
            del img_buf

            if img_file:
                oiio.ImageCache().invalidate(img_file.as_posix())
        except Exception as e:
            LOGGER.error('Error closing img buf: %s', e)
