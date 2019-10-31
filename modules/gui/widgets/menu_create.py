from typing import List, Union

from PySide2.QtCore import Slot, Qt
from PySide2.QtWidgets import QMainWindow, QMenu, QAction, QActionGroup

from modules.gui.ui_resource import IconRsc
from modules.idgen import KnechtUuidGenerator as Kid
from modules.itemview.editor_create import ItemTemplates
from modules.itemview.item import KnechtItem
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.knecht_camera import KnechtImageCameraInfo
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class CreateMenu(QMenu):

    def __init__(self, parent_widget, menu_name: str=_("Erstellen")):
        super(CreateMenu, self).__init__(menu_name, parent_widget)
        self.parent_widget = parent_widget
        self.current_view = None
        i = IconRsc

        self.create_action_grp = QActionGroup(self)
        self.create_action_grp.setExclusive(False)

        # -- Create User Preset from selection action
        self.user_preset_from_selected = QAction(i.get_icon('preset'),
                                                 _('User Preset aus Selektion'),
                                                 self.create_action_grp)
        self.user_preset_from_selected.triggered.connect(
            self._create_user_preset_from_selected
            )

        # -- Create Render Preset from selection action
        self.render_preset_from_selected = QAction(i.get_icon('render'),
                                                   _('Render Preset aus Selektion'),
                                                   self.create_action_grp)
        self.render_preset_from_selected.triggered.connect(
            self._create_render_preset_from_selected
            )

        action_list = [(_("Render Preset\tEnthält User Presets, Viewsets und Rendereinstellungen"),
                       i.get_icon('render'), self._create_render_preset_from_selected),
                       (_("User Preset\tEnthält Varianten und/oder Referenzen"),
                        i.get_icon('preset'), self._create_user_preset_from_selected),
                       (_("Viewset\tEnthält **eine** Shot Variante"),
                       i.get_icon('viewset'), self._create_viewset),
                       (_("Reset\tVarianten für eine Resetschaltung"),
                       i.get_icon('reset'), self._create_reset),
                       (_("Trimline Preset\tVarianten für eine Serienschaltung"),
                       i.get_icon('car'), self._create_trimline),
                       (_("Paket Preset\tVarianten eines Pakets"),
                       i.get_icon('pkg'), self._create_package),
                       (_("FaKom Serien\tVarianten einer Serien Farbkombination"),
                       i.get_icon('fakom_trim'), self._create_fakom_trim),
                       (_("FaKom Option\tVarianten einer Farbkombination"),
                       i.get_icon('fakom'), self._create_fakom_option),
                       (_('Ausgabe Objekt\tDefiniert einen Ausgabepfad'),
                        i.get_icon('folder'), self._create_output_item),
                       (_('PlmXml Objekt\tDefiniert einen Pfad zur PlmXml Datei'), i.get_icon('assignment'),
                        self._create_plmxml_item),
                       (_('Kamera Objekt\tEnthält 3DS DeltaGen Kameradaten'), i.get_icon('videocam'),
                       self._create_camera_item),
                       (_("Separator\tNicht-interagierbares Ordnungselement"),
                       i.get_icon('navicon'), self._create_separator)
                       ]

        for a in action_list:
            name, icon, method_call = a
            action = QAction(icon, name, self.create_action_grp)
            action.triggered.connect(method_call)
            self.addAction(action)

        self.aboutToShow.connect(self.update_current_view)

    def _create_user_preset_from_selected(self):
        self._create_preset_from_selected(is_user_preset=True)

    def _create_render_preset_from_selected(self):
        rp = self._create_preset_from_selected(is_user_preset=False)
        if rp:
            LOGGER.debug('RP ID: %s', rp.data(Kg.ID))

    def _create_preset_from_selected(self, is_user_preset: bool=True) -> Union[None, KnechtItem]:
        """ Copy and create a preset from selected items """
        if not self.current_view:
            LOGGER.error('Can not find view in focus to add items to.')
            return

        child_items = self.current_view.editor.copypaste.copy_preset_items_from_selection()

        if is_user_preset:
            return self.current_view.editor.create.create_preset_from_items(child_items)
        else:
            return self.current_view.editor.create.create_render_preset_from_items(child_items)

    def _create_camera_item(self):
        if not self.current_view:
            return

        name = _('DeltaGen_Kamera_{:03d}').format(self.current_view.editor.create.item_count)
        self.current_view.editor.create.item_count += 1

        new_item = self.current_view.editor.create.create_camera_item(name, KnechtImageCameraInfo.camera_example_info)
        self.current_view.editor.create_top_level_rows([new_item])

    def _create_viewset(self):
        self._create_item(ItemTemplates.viewset)

    def _create_reset(self):
        self._create_item(ItemTemplates.reset)

    def _create_trimline(self):
        self._create_item(ItemTemplates.trim)

    def _create_package(self):
        self._create_item(ItemTemplates.package)

    def _create_fakom_trim(self):
        self._create_item(ItemTemplates.fakom_trim)

    def _create_fakom_option(self):
        self._create_item(ItemTemplates.fakom_option)

    def _create_output_item(self):
        self._create_item(ItemTemplates.output)

    def _create_plmxml_item(self):
        self._create_item(ItemTemplates.plmxml)

    def _create_separator(self):
        self._create_item(ItemTemplates.separator, False)

    def _create_item(self, item, create_id: bool=True):
        if not self.current_view:
            LOGGER.error('Can not find view in focus to add items to.')
            return

        self.current_view.editor.create.add_item(item, create_id=create_id)

    @Slot()
    def update_current_view(self):
        current_view = None

        if isinstance(self.parent_widget, QMainWindow):
            current_view = self.parent_widget.view_mgr.current_view()
            self.create_action_grp.setEnabled(True)
            LOGGER.debug('Create Menu about to show from Main Window Menu.')
        elif isinstance(self.parent_widget, QMenu):
            current_view = self.parent_widget.view
            self.create_action_grp.setEnabled(True)
            LOGGER.debug('Create Menu about to show from Context Menu.')

        if current_view.is_render_view:
            self.create_action_grp.setEnabled(False)

        self.current_view = current_view
