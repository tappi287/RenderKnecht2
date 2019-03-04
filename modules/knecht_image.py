from pathlib import Path
from threading import Thread
from typing import Union, List

from PySide2.QtCore import QObject, Signal
import numpy as np
from imageio import imread, imwrite

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

    def convert_directory(self, img_dir: Path, output_dir: Path=Path('.'),
                          output_format: str='.png', move_converted: bool=False) -> bool:
        if not img_dir.exists():
            return False

        img_list = list()
        for file in img_dir.glob('*.*'):
            if file.suffix.casefold() in self.supported_image_types:
                img_list.append(file)

        if not img_list:
            return False

        img_thread = ConversionThread(img_list, self.conversion_result, output_dir, output_format, move_converted)
        img_thread.start()
        return True

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

            if not self.output_dir.exists():
                try:
                    self.output_dir.mkdir(parents=True)
                except Exception as e:
                    result += _('Konnte Ausgabe Verzeichnis nicht erstellen: {}\n').format(e)
                    break

            # Open and convert image
            try:
                img = KnechtImage.open_with_imageio(img_file)
            except Exception as e:
                result += _('Konnte Bilddatei {} nicht konvertieren: {}\n').format(img_file.name, e)
                continue

            # Write image to file
            try:
                img_out = self.output_dir / Path(img_file.stem).with_suffix(self.output_format)
                imwrite(img_out, img)
                result += _('Bilddatei erstellt: {}\n').format(img_out.name)
            except Exception as e:
                result += _('Konnte Bilddatei {} nicht erstellen: {}\n').format(img_file.name, e)
                continue

            # Move source files
            if not self.move_converted:
                continue

            # Create un-converted directory
            move_dir = self.output_dir.parent / self.unconverted_dir_name
            if not move_dir.exists():
                move_dir.mkdir(parents=True)

            # Move the file to un-converted directory
            try:
                img_file.replace(move_dir / img_file.name)
                LOGGER.debug('Moving un-converted image file: %s', img_file.name)
            except FileNotFoundError or FileExistsError:
                result += _('Konnte unkonvertierte Bilddatei nicht verschieben: {}\n').format(img_file.name)
                pass

        self.result_signal.emit(result)
