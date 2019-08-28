from typing import List, Union

from PySide2.QtCore import Slot, Qt
from PySide2.QtWidgets import QMainWindow, QMenu, QAction, QActionGroup

from modules.gui.ui_resource import IconRsc
from modules.idgen import KnechtUuidGenerator as Kid
from modules.itemview.item import KnechtItem
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.knecht_image import KnechtImageCameraInfo
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

        self.item_count = 0

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
                        i.get_icon('folder'), self._create_output_item), (
                       _('Kamera Objekt\tEnthält 3DS DeltaGen Kameradaten'), i.get_icon('videocam'),
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
        self._create_preset_from_selected(is_user_preset=False)

    def _create_preset_from_selected(self, is_user_preset: bool=True):
        """ Copy and create a preset from selected items """
        if not self.current_view:
            LOGGER.error('Can not find view in focus to add items to.')
            return

        child_items = self.current_view.editor.copypaste.copy_preset_items_from_selection()

        if is_user_preset:
            self._create_user_preset(child_items)
        else:
            self._create_render_preset(child_items)

    def _create_render_preset(self, preset_children: List[KnechtItem]=None):
        children = list()
        children.append(self._create_item('Anti-Aliasing Samples', '512', 'sampling', '', '',
                        'Setzt das globale Sampling Level. Benutzt Clamping Einstellungen der geladenen Szene!'))
        children.append(self._create_item('Datei Erweiterung', '.hdr', 'file_extension', '', '',
                        'Setzt die Ausgabe Dateiendung. HDR wird als 8bit ausgegeben und '
                        'berücksichtigt Viewport Display Adaption.'))
        children.append(self._create_item('Auflösung', '2560 1920', 'resolution', '', '',
                        'Auflösung kann auch manuell, mit einem Leerzeichen getrennt, eingegeben werden: X Y'))

        children += preset_children or []

        self._add_item('Render_Preset', ('', Kg.type_keys[Kg.render_preset]), children)

    def _create_user_preset(self, preset_children: list=None):
        self._add_item('User_Preset', ('', Kg.type_keys[Kg.preset]), preset_children, _id=True)

    def _create_viewset(self):
        children = list()
        children.append(self._create_item('#_Shot', 'Shot_00', '', '', '', 'Schalter des Shot Varianten Sets'))
        self._add_item('Viewset', ('', 'viewset'), children, _id=True)

    def _create_camera_item(self):
        children = list()

        for k, v in KnechtImageCameraInfo.camera_example_info.items():
            children.append(
                self._create_item(k, v, '', '', '', KnechtImageCameraInfo.rtt_camera_desc.get(k) or '')
                )

        self._add_item(_('DeltaGen Kamera'), ('', 'camera_item'), children, _id=True)

    def _create_reset(self):
        children = list()
        children.append(self._create_item(
            'reset', 'on', '', '', '', 'Sollte einen im Modell vorhanden Reset Schalter betätigen'))
        children.append(self._create_item(
            'reset', 'off', '', '', '', 'Sollte einen im Modell vorhanden Reset Schalter betätigen'))
        children.append(self._create_item(
            'RTTOGLRT', 'on', '', '', '', 'Benötigte Optionen müssen nach dem Reset erneut geschaltet werden.'))

        self._add_item('Reset', ('', 'reset'), children, _id=True)

    def _create_trimline(self):
        children = list()
        children.append(self._create_item('Motorschalter', 'on', '', '', '', 'Variante des Modells'))
        children.append(self._create_item('Serien_Optionen', 'on', '', '', '', 'Varianten der Serienumfänge'))
        self._add_item('OEM Derivat Form Trimline Motor', ('', 'trim_setup'), children, _id=True)

    def _create_package(self):
        children = list()
        children.append(self._create_item('Paket_Variante', 'on', '', '', '', 'Varianten der Paket Option'))
        self._add_item('Paket', ('', 'package'), children, _id=True)

    def _fakom_children(self):
        children = list()
        children.append(self._create_item('XX_Farbschluessel', 'on', '', '', '', 'Zweistelliger Farbschluessel'))
        children.append(self._create_item('PRN_Sitzbezug', 'on', 'SIB', '', '', 'Sitzbezug Option'))
        children.append(self._create_item('PRN_Vordersitze', 'on', 'VOS', '', '', 'Sitzart Option'))
        children.append(self._create_item('PRN_Lederumfang', 'on', 'LUM', '', '', 'Lederpaket Option'))
        return children

    def _create_fakom_trim(self):
        children = self._fakom_children()
        self._add_item('FaKom Modell PR_SIB_VOS_LUM', ('', 'fakom_setup'), children, _id=True)
        
    def _create_fakom_option(self):
        children = self._fakom_children()
        self._add_item('FaKom Modell PR_SIB_VOS_LUM Option', ('', 'fakom_option'), children, _id=True)

    def _create_output_item(self):
        self._add_item(_('Ausgabe Pfad'), (_('<Kein Pfad gesetzt>'), 'output_item'), None, _id=True)

    def _create_separator(self):
        self._add_item('', ('', 'separator'))
        
    @staticmethod
    def _create_item(*data):
        return KnechtItem(None, data=('123', *data))
        
    def _add_item(self, name: str, data: tuple, children: Union[None, List]=None, _id: bool=False):
        if not self.current_view:
            LOGGER.error('Can not find view in focus to add items to.')
            return

        self.item_count += 1

        if name:
            name = f'{name}_{self.item_count:03d}'

        new_item = KnechtItem(
            None, ('000', name, *data)
            )

        if _id:
            # Create unique item id
            new_item.setData(Kg.ID, Kid.create_id())

        for idx, child_item in enumerate(children or []):
            child_item.setData(Kg.ORDER, f'{idx:03d}', Qt.DisplayRole)
            new_item.append_item_child(child_item)

        self.current_view.editor.create_top_level_rows([new_item])

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
