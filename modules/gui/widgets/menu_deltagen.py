from PySide2 import QtCore
from PySide2.QtCore import Slot
from PySide2.QtGui import QIcon
from PySide2.QtWidgets import QAction, QMenu, QActionGroup, QApplication

from modules.gui.ui_resource import IconRsc
from modules.gui.widgets.menu_asscene import AsSceneMenu
from modules.language import get_translation
from modules.log import init_logging
from modules.settings import KnechtSettings

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class DeltaGenMenu(QMenu):

    def __init__(self, ui, menu_name: str = _('DeltaGen')):
        """ Setup the DeltaGen MainMenu setting KnechtSettings for DeltaGen communication

        :param modules.gui.main_ui.KnechtWindow ui:
        :param menu_name: name of the menu that will be displayed
        """
        super(DeltaGenMenu, self).__init__(menu_name, ui)
        self.ui = ui

        self.reset, self.freeze, self.check = None, None, None

        self.hidden_actions = QActionGroup(self)
        self.hidden_actions.setVisible(False)

        self.send_camera, self.display, self.display_overlay = None, None, None
        self.enable_material_dummy, self.validate_plmxml = None, None
        self.as_scene_menu = QMenu()

        self.setup_deltagen_menu()

        # Apply settings before showing
        self.aboutToShow.connect(self._menu_about_to_show)

    def setup_deltagen_menu(self):
        # ---- Reset On/Off ----
        self.reset = self._setup_checkable_action(_('Reset senden'), True, self.toggle_reset)

        # ---- Freeze Viewer On/Off ----
        self.freeze = self._setup_checkable_action(_('Freeze Viewer'), True, self.toggle_freeze_viewer)

        # ---- Variants State Check On/Off ----
        self.check = self._setup_checkable_action(_('Varianten State Check'), True, self.toggle_variants_state_check)

        # ---- Send Camera Data On/Off ----
        self.send_camera = self._setup_checkable_action(_('Kamera Daten übertragen'), True, self.toggle_camera_send)

        # ---- Display State Check On/Off ----
        self.display = self._setup_checkable_action(_('State Check im Baum anzeigen'), False,
                                                    self.toggle_state_check_display)

        # ---- Display Overlay after Preset Send operation finished ----
        self.display_overlay = self._setup_checkable_action(_('Zuletzt gesendetes Preset als Overlay anzeigen'), False,
                                                            self.toggle_display_finished_overlay)

        # ---- Assign Dummy Material before applying PlmXml Materials
        self.enable_material_dummy = self._setup_checkable_action(_('Dummy Material auf PlmXml Konfiguration anwenden'),
                                                                  False, self.toggle_plmxml_material_dummy)

        # ---- Validate DeltaGen Scene vs PlmXml before switching configurations
        self.validate_plmxml = self._setup_checkable_action(
            _('DeltaGen Szene vor dem konfigurieren mit PlmXml abgleichen.'), True,
            self.toggle_validate_plmxml, self.hidden_actions)

        # --- As Connector choose active scene menu ---
        self.as_scene_menu.deleteLater()
        self.as_scene_menu = AsSceneMenu(self.ui, _('AsConnector aktive Szene:'))
        self.addMenu(self.as_scene_menu)

        self._apply_settings()

    def _setup_checkable_action(self, name: str, checked: bool, target: object, action_grp: QActionGroup = None):
        check_icon = IconRsc.get_icon('check_box_empty')
        check_icon.addPixmap(IconRsc.get_pixmap('check_box'), QIcon.Normal, QIcon.On)

        if action_grp:
            action = QAction(check_icon, name, action_grp)
        else:
            action = QAction(check_icon, name, self)
        action.setCheckable(True)
        action.setChecked(checked)
        action.triggered.connect(target)
        self.addAction(action)

        return action

    def _menu_about_to_show(self):
        """ Setup method before menu is visible """
        # Hide hidden actions
        self.hidden_actions.setVisible(False)

        # Show hidden actions with Ctrl Key
        if QApplication.keyboardModifiers() & QtCore.Qt.ControlModifier:
            self.hidden_actions.setVisible(True)

        self._apply_settings()

    def _apply_settings(self):
        """ Apply saved settings """
        self.reset.setChecked(KnechtSettings.dg.get('reset'))
        self.freeze.setChecked(KnechtSettings.dg.get('freeze_viewer'))
        self.check.setChecked(KnechtSettings.dg.get('check_variants'))
        self.send_camera.setChecked(KnechtSettings.dg.get('send_camera_data'))
        self.display.setChecked(KnechtSettings.dg.get('display_variant_check'))
        self.display_overlay.setChecked(KnechtSettings.dg.get('display_send_finished_overlay'))
        self.enable_material_dummy.setChecked(KnechtSettings.dg.get('use_material_dummy'))
        self.validate_plmxml.setChecked(KnechtSettings.dg.get('validate_plmxml_scene'))

    @Slot(bool)
    def toggle_reset(self, checked: bool):
        LOGGER.debug('Received from: %s', self.sender().text())
        KnechtSettings.dg['reset'] = checked

    @Slot(bool)
    def toggle_freeze_viewer(self, checked: bool):
        KnechtSettings.dg['freeze_viewer'] = checked

    @Slot(bool)
    def toggle_variants_state_check(self, checked: bool):
        KnechtSettings.dg['check_variants'] = checked

    @Slot(bool)
    def toggle_state_check_display(self, checked: bool):
        KnechtSettings.dg['display_variant_check'] = checked

    @Slot(bool)
    def toggle_display_finished_overlay(self, checked: bool):
        KnechtSettings.dg['display_send_finished_overlay'] = checked

    @Slot(bool)
    def toggle_plmxml_material_dummy(self, checked: bool):
        KnechtSettings.dg['use_material_dummy'] = checked

    @Slot(bool)
    def toggle_validate_plmxml(self, checked: bool):
        KnechtSettings.dg['validate_plmxml_scene'] = checked

    @Slot(bool)
    def toggle_camera_send(self, checked: bool):
        KnechtSettings.dg['send_camera_data'] = checked

    def enable_menus(self, enabled: bool = True):
        for a in self.menu.actions():
            a.setEnabled(enabled)
