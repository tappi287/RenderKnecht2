from PySide2.QtCore import QTimer, Slot
from PySide2.QtGui import QIcon
from PySide2.QtWidgets import QAction, QMenu

from modules.settings import KnechtSettings
from modules.gui.ui_resource import IconRsc
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class DeltaGenMenu(QMenu):
    new_document_count = 0
    load_save_mgr = None

    def __init__(self, ui, menu_name: str = _('DeltaGen')):
        """ Setup the DeltaGen MainMenu setting KnechtSettings for DeltaGen communication

        :param modules.gui.main_ui.KnechtWindow ui:
        :param menu_name: name of the menu that will be displayed
        """
        super(DeltaGenMenu, self).__init__(menu_name, ui)
        self.ui = ui

        self.reset, self.freeze, self.check, self.display = None, None, None, None

        self.setup_deltagen_menu()
        QTimer.singleShot(1, self.delayed_setup)

        # Apply settings before showing
        self.aboutToShow.connect(self._apply_settings)

    @Slot()
    def delayed_setup(self):
        """ Setup attributes that require a fully initialized ui"""
        pass

    def setup_deltagen_menu(self):
        # ---- Reset On/Off ----
        self.reset = self._setup_checkable_action(_('Reset senden'), True, self.toggle_reset)

        # ---- Freeze Viewer On/Off ----
        self.freeze = self._setup_checkable_action(_('Freeze Viewer'), True, self.toggle_freeze_viewer)

        # ---- Variants State Check On/Off ----
        self.check = self._setup_checkable_action(_('Varianten State Check'), True, self.toggle_variants_state_check)

        # ---- Display State Check On/Off ----
        self.display = self._setup_checkable_action(_('State Check im Baum anzeigen'), False,
                                                    self.toggle_state_check_display)

    def _setup_checkable_action(self, name: str, checked: bool, target: object):
        check_icon = IconRsc.get_icon('check_box_empty')
        check_icon.addPixmap(IconRsc.get_pixmap('check_box'), QIcon.Normal, QIcon.On)

        action = QAction(check_icon, name, self)
        action.setCheckable(True)
        action.setChecked(checked)
        action.triggered.connect(target)
        self.addAction(action)

        return action

    def _apply_settings(self):
        """ Apply saved settings """
        self.reset.setChecked(KnechtSettings.dg['reset'])
        self.freeze.setChecked(KnechtSettings.dg['freeze_viewer'])
        self.check.setChecked(KnechtSettings.dg['check_variants'])
        self.display.setChecked(KnechtSettings.dg['display_variant_check'])

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

    def enable_menus(self, enabled: bool=True):
        for a in self.menu.actions():
            a.setEnabled(enabled)
