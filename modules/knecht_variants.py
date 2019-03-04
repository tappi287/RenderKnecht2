import re
from pathlib import Path
from typing import List, Tuple

from PySide2.QtCore import QModelIndex


def create_file_safe_name(filename: str) -> str:
    """ Replace any non alphanumeric characters from a string expect minus/underscore/period """
    return re.sub('[^\\w\\-_\\.]', '_', filename)


class KnechtVariant:
    def __init__(self, index: QModelIndex, name: str, value: str):
        """ DeltaGen Variant including the model index referred too

        :param QModelIndex index: The model index this Variant refers too
        :param str name: The name of the Variant Set
        :param str value: The Variant inside the Variant Set
        """
        self.index = index
        self.name = name
        self.value = value

        self.name_valid = False
        self.value_valid = False

    def set_name_valid(self):
        self.name_valid = True

    def set_name_invalid(self):
        self.name_valid = False

    def set_value_valid(self):
        self.value_valid = True

    def set_value_invalid(self):
        self.value_valid = False


class KnechtVariantList:
    def __init__(self):
        self.variants = list()

    def add(self, index: QModelIndex, name: str, value: str) -> None:
        """ Add a single variant to the list of variants

        :param index: The source model index of this variant
        :param name: The Variant Set name
        :param value: The Variant inside the Variant Set
        :return: None
        """
        variant = KnechtVariant(index, name, value)
        self.variants.append(variant)

    def __add__(self, other_variant_list):
        """ Addition variants of another KnechtVariantList """
        if isinstance(other_variant_list, KnechtVariantList):
            new_ls = KnechtVariantList()
            new_ls.variants = self.variants[::]
            new_ls.variants += other_variant_list.variants
            return new_ls
        elif isinstance(other_variant_list, KnechtVariant):
            self.variants.append(other_variant_list)
            return self

    def __len__(self):
        return len(self.variants)


class RenderImage:
    def __init__(self, name: str, variants: KnechtVariantList):
        """ Holds information about the image name and variants to switch for this render image """
        self.name = create_file_safe_name(name)
        self.variants = variants


class RenderShot:
    def __init__(self, name: str, variants: KnechtVariantList):
        """ Holds information about one shot setting.

            Render images can be rendered in different shots
            eg. Render_Image_one_Shot-01, Render_Image_one_Shot-02, etc.
        """
        self.name = create_file_safe_name(name)
        self.variants = variants


class KnechtRenderPreset:
    def __init__(self, name: str='Render_Preset'):
        self.name = create_file_safe_name(name)

        self.settings = dict(
            sampling=1,
            file_extension='.hdr',
            resolution='2560 1920'
            )

        self.path = Path('.')

        # Keep a list of rendering paths above the 256 chrs limit
        self.too_long_paths = list()

        self.__image_count = 0

        self.__images = list()
        self.__shots = list()

        # Images per shot
        # will be created upon every image or shot addition
        self.__render_images = list()

    @property
    def shots(self):
        return self.__shots

    @shots.setter
    def shots(self, val: Tuple[str, KnechtVariantList]):
        """
        Add an render shot to the render preset containing the shot name and variants as tuple.

        :param Tuple[str, KnechtVariantList] val: name as string, list of variants to switch
        :return: None
        """
        name, variants = val
        new_image = RenderShot(name, variants)

        self.__shots.append(new_image)

        # Update list of images to render
        self.__create_render_images_list()

    def add_shot(self, name: str, variants: KnechtVariantList):
        """
        Add an render shot to the render preset containing the shot name and variants to switch.

        :param name: string name
        :param variants: list of variants to switch
        :return: None
        """
        self.shots = (name, variants)

    @property
    def images(self):
        return self.__images

    @images.setter
    def images(self, val: Tuple[str, KnechtVariantList]):
        """
        Add an render image to the render preset containing the image name and variants as tuple.

        :param Tuple[str, KnechtVariantList] val: name as string, list of variants to switch
        :return: None
        """
        name, variants = val
        new_image = RenderImage(name, variants)

        self.__images.append(new_image)

        # Update list of images to render
        self.__create_render_images_list()

    def add_image(self, name: str, variants: KnechtVariantList):
        """
        Add an render image to the render preset containing the image name and variants to switch.

        :param name: string name
        :param variants: list of variants to switch
        :return: None
        """
        self.images = (name, variants)

    def verify_path_lengths(self) -> bool:
        """ Iterate render images and return False if any Path is above path limit """
        self.too_long_paths = list()

        for (image, shot) in self.__render_images:
            img_file_name = f'{self.__image_name(image, shot)}{self.settings.get("file_extension")}'
            img_path = self.path / img_file_name

            if len(str(img_path)) >= 259:
                self.too_long_paths.append(img_path)

        if self.too_long_paths:
            return False
        return True

    def __create_render_images_list(self):
        """
            Create the list of render images that need to be created
            eg. Render_Image_one_Shot-01, Render_Image_one_Shot-02, etc.
        """
        self.__render_images = list()

        for image in self.images:
            if not self.shots:
                dummy_shot = RenderShot('', KnechtVariantList())
                self.__render_images.append((image, dummy_shot))

            for shot in self.shots:
                self.__render_images.append((image, shot))
        return

    def __create_render_image(self) -> Tuple[str, KnechtVariantList]:
        __r: Tuple[RenderImage, RenderShot] = self.__render_images.pop(0)
        image: RenderImage = __r[0]
        shot: RenderShot = __r[1]

        image_name = self.__image_name(image, shot)

        return image_name, image.variants + shot.variants

    def __image_name(self, image: RenderImage, shot: RenderShot) -> str:
        """ Create the image name based on image name and shot name """
        image_name = f'{self.__image_count:03d}_{image.name}'

        if shot.name:
            image_name += f'_{shot.name}'

        return image_name

    def remaining_images(self) -> int:
        """ The number of render images that still need to be rendered """
        return len(self.__render_images)

    def image_count(self) -> int:
        """ The number of render images that will be created. """
        return max(1, len(self.shots)) * len(self.images)

    def current_image_number(self) -> int:
        return self.__image_count

    def get_next_render_image(self) -> Tuple[str, KnechtVariantList]:
        """
        Get the next render image name and variants.

        :return Tuple[str, KnechtVariantList]: (name, variants list)
        """
        if not self.remaining_images():
            return '', KnechtVariantList()

        image_name, image_variants = self.__create_render_image()
        self.__image_count += 1

        return image_name, image_variants
