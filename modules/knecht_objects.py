import re
import time
from pathlib import Path
from typing import List, Tuple, Union

from PySide2.QtCore import QModelIndex

from modules.gui.widgets.path_util import path_exists
from modules.knecht_fakom import FakomData
from modules.log import init_logging

LOGGER = init_logging(__name__)


def create_file_safe_name(filename: str) -> str:
    """ Replace any non alphanumeric characters from a string expect minus/underscore/period """
    return re.sub('[^\\w\\-_\\.]', '_', filename)


class KnechtVariant:
    def __init__(self, index: QModelIndex, name: str, value: str, item_type: str=''):
        """ DeltaGen Variant including the model index referred too

        :param QModelIndex index: The model index this Variant refers too
        :param str name: The name of the Variant Set
        :param str value: The Variant inside the Variant Set
        :param str item_type:
        """
        self.index = index
        self.name = name
        self.value = value
        self.item_type = item_type

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
        self.variants: List[KnechtVariant] = list()
        self.output_path = None

    def add(self, index: QModelIndex, name: str, value: str, item_type: str='') -> None:
        """ Add a single variant to the list of variants

        :param index: The source model index of this variant
        :param name: The Variant Set name
        :param value: The Variant inside the Variant Set
        :param item_type: Optional type description that refers to PR-Family for PR-Option items
        :return: None
        """
        if item_type == 'output_item':
            self.output_path = value
            return

        variant = KnechtVariant(index, name, value, item_type)
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


class _RenderImage:
    def __init__(self, name: str, variants: KnechtVariantList):
        """ Holds information about the image name and variants to switch for this render image """
        self.name = create_file_safe_name(name)
        self.variants = variants
        self.path = Path('.')


class _RenderShot:
    def __init__(self, name: str, variants: KnechtVariantList):
        """ Holds information about one shot setting.

            Render images can be rendered in different shots
            eg. Render_Image_one_Shot-01, Render_Image_one_Shot-02, etc.
        """
        self.name = create_file_safe_name(name)
        self.variants = variants


class KnechtRenderPreset:
    def __init__(self, name: str = 'Render_Preset', ui_path: Path=Path('.')):
        self.name = create_file_safe_name(name)

        self.settings = dict(
            sampling=1,
            file_extension='.hdr',
            resolution='2560 1920'
            )

        self.unique_out_dir_name = 'out_' + str(time.time())[:19]
        self.create_preset_dir = False

        self.path = ui_path

        # Keep a list of rendering paths above the 256 chrs limit
        self.too_long_paths = list()
        # Keep a list of rendering paths that could not be created or could not be written too
        self.invalid_paths: List[str] = list()

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
        new_image = _RenderShot(name, variants)

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
        new_image = _RenderImage(name, variants)

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
            out_dir_name = 'out_0123456789012345678'
            img_path = self._get_output_dir(image, shot, create_dir=False) / out_dir_name / img_file_name

            if len(img_path.as_posix()) >= 258:
                self.too_long_paths.append(img_path)

        if self.too_long_paths:
            return False
        return True

    def verify_output_paths(self) -> bool:
        """ Iterate render images and return False if any Path is invalid """
        self.invalid_paths: List[str] = list()

        for (image, shot) in self.__render_images:
            try:
                img_path = self._get_output_dir(image, shot, create_dir=True)
                if not img_path.exists():
                    self.invalid_paths.append(str(img_path))
            except Exception as e:
                LOGGER.error('Error creating or verifying output path: %s', e)
                self.invalid_paths.append(str(e))

        if self.invalid_paths:
            return False
        return True

    def _get_output_dir(self, image: _RenderImage, shot: _RenderShot, create_dir=True) -> Path:
        out_dir = self.path

        if shot.variants.output_path:
            out_dir = Path(shot.variants.output_path)
        if image.variants.output_path:
            out_dir = Path(image.variants.output_path)

        if self.create_preset_dir:
            out_dir = out_dir / self.name

        if create_dir:
            out_dir = self.create_directory(out_dir)

        return out_dir

    def create_directory(self, render_dir):
        render_dir = Path(render_dir) / self.unique_out_dir_name

        if not path_exists(render_dir):
            try:
                render_dir.mkdir(parents=True)
            except Exception as e:
                LOGGER.critical('Could not create rendering directory! Rendering to executable path.\n%s', e)
                render_dir = Path('.') / self.unique_out_dir_name

                try:
                    render_dir.mkdir(parents=True)
                except Exception as e:
                    LOGGER.critical('Could not create fallback directory! '
                                    'Rendering will not be able to write images.\n%s', e)

        return render_dir

    def __create_render_images_list(self):
        """
            Create the list of render images that need to be created
            eg. Render_Image_one_Shot-01, Render_Image_one_Shot-02, etc.
        """
        self.__render_images = list()

        for image in self.images:
            if not self.shots:
                dummy_shot = _RenderShot('', KnechtVariantList())
                self.__render_images.append((image, dummy_shot))

            for shot in self.shots:
                self.__render_images.append((image, shot))
        return

    def __create_render_image(self) -> Tuple[str, KnechtVariantList, Path]:
        __r: Tuple[_RenderImage, _RenderShot] = self.__render_images.pop(0)
        image: _RenderImage = __r[0]
        shot: _RenderShot = __r[1]

        image_name = self.__image_name(image, shot)

        return image_name, image.variants + shot.variants, self._get_output_dir(image, shot)

    def __image_name(self, image: _RenderImage, shot: _RenderShot) -> str:
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

    def get_next_render_image(self) -> Tuple[str, KnechtVariantList, Path]:
        """
        Get the next render image name and variants.

        :return Tuple[str, KnechtVariantList]: (name, variants list)
        """
        if not self.remaining_images():
            return '', KnechtVariantList(), self.path

        image_name, image_variants, out_dir = self.__create_render_image()
        self.__image_count += 1

        return image_name, image_variants, out_dir


class _DataTrimOption:
    def __init__(self, parent=None, name=None, desc=None, family=None, family_desc=None, value=None):
        """
        The base class for PR-Options and Packages.
        """
        self.name = name or ''
        self.desc = desc or ''
        self.family = family or ''
        self.family_desc = family_desc or ''
        self.value = value

        self.parent: Union[_DataParent, None] = parent

        if self.parent is not None:
            self.parent.children.append(self)

    def num(self) -> int:
        """ Returns this items number in it's parent child list """
        if self.parent:
            if hasattr(self.parent, 'children'):
                if isinstance(self.parent.children, list):
                    self.parent.children: list
                    return self.parent.children.index(self)

        return 0


class _DataParent:
    PR_TRIM_FILTER = ('L', 'I')     # Excel cell content that indicates an option belongs to default trim
    PR_OPT_FILTER = ('E',)          # Excel cell content that clearly indicates an option is optional
    PR_UNAVAILABLE_FILTER = ('-',)  # Excel cell content that clearly indicates an option is unavailable

    def __init__(self):
        """ Data Item that can have PR/Package children """
        self.children: List[_DataTrimOption] = list()

    def iterate_children(self):
        yield from self.children

    def iterate_pr(self):
        for c in self.children:
            if type(c) is KnPr:
                yield c

    def iterate_packages(self):
        """

        :return: KnPackage
        """
        for c in self.children:
            if type(c) is KnPackage:
                yield c

    def iterate_available_pr(self):
        """
        Return PR-Options -NOT- matching Unavailable filter

        :return KnPr
        """
        for c in self.iterate_pr():
            if c.value and c.value not in self.PR_UNAVAILABLE_FILTER:
                yield c

    def iterate_trim_pr(self):
        """
        Return PR-Options -EXACTLY- matching Trim filter

        :return KnPr
        """
        for c in self.iterate_pr():
            if c.value in self.PR_TRIM_FILTER:
                yield c

    def iterate_optional_pr(self):
        """
        Return PR-Options -NOT- matching Trim or Unavailable filters

        :return KnPr
        """
        for c in self.iterate_pr():
            if c.value not in self.PR_TRIM_FILTER and c.value not in self.PR_UNAVAILABLE_FILTER:
                yield c

    def iterate_optional_filtered_pr(self):
        """
        Return PR-Options -EXACTLY- matching the PR_OPT_FILTER

        :return KnPr
        """
        for c in self.iterate_pr():
            if c.value in self.PR_OPT_FILTER:
                yield c

    def child_count(self):
        return len(self.children)


class _DataTrim(_DataParent):
    def __init__(self,
                 market='Markt',
                 market_text='Markttext',
                 modelyear='Modelljahr',
                 model_class='Klasse',
                 model_class_text='Klassentext',
                 derivate='Derivat',
                 model='Modell',
                 version='Version',
                 status='Status',
                 model_text='Modelltext',
                 start='Einsatz',
                 end='Entfall',
                 engine_size='Hubraum',
                 engine_power='Leistung',
                 gearbox='Getriebe'
                 ):
        super(_DataTrim, self).__init__()

        self.market = market
        self.market_text = market_text
        self.modelyear = modelyear
        self.model_class = model_class
        self.model_class_text = model_class_text
        self.derivate = derivate
        self.model = model
        self.version = version
        self.status = status
        self.model_text = model_text
        self.start = start
        self.end = end
        self.engine_size = engine_size
        self.engine_power = engine_power
        self.gearbox = gearbox


class _DataColumns:
    def __init__(self, cls_object):
        """ This will create the same class property/attributes for this class as in cls_object
            but will save a column integer value instead of the attribute value.
            Eg. class.name = 0 instead of class.name = 'somename'

        :param cls_object:
        """
        idx = 0
        for attr in dir(cls_object):
            if not attr.startswith('__'):
                setattr(self, attr, idx)
                idx += 1


class KnPr(_DataTrimOption):
    """ Knecht PR-Option """
    pass


class KnPrFam(_DataTrimOption, _DataParent):
    """ Knecht PR-Family """
    def __init__(self, parent=None, name=None, desc=None, family=None, family_desc=None, value=None):
        _DataTrimOption.__init__(self, parent, name, desc, family, family_desc, value)
        _DataParent.__init__(self)


class KnPackage(_DataTrimOption, _DataParent):
    """ Knecht Package """
    def __init__(self, parent=None, name=None, desc=None, family=None, family_desc=None, value=None):
        _DataTrimOption.__init__(self, parent, name, desc, family, family_desc, value)
        _DataParent.__init__(self)


class KnTrim(_DataTrim):
    pass


class KnData:
    def __init__(self):
        self.models: List[KnTrim] = list()
        self.pr_families: List[KnPrFam] = list()
        self.fakom: FakomData = FakomData()

        # Ui options - will be set by the excel dialog
        # and be used by the excel-to-model module
        # These options do not matter until model creation. We will
        # keep the complete set of data.
        self.read_trim = False
        self.read_options = False
        self.options_text_filter = False  # Read only PR-Options explicity matching "E"
        self.read_packages = False
        self.read_fakom = False
        self.pr_fam_filter_packages = False

        self.selected_models = list()
        self.selected_pr_families = list()
