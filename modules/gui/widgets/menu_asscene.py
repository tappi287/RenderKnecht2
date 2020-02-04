from PySide2.QtCore import QTimer
from PySide2.QtWidgets import QMenu, QAction, QActionGroup

from modules.gui.ui_resource import IconRsc
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class AsSceneMenu(QMenu):

    def __init__(self, ui, menu_name: str = _('DeltaGen')):
        """ Setup AsConnector Scene Selection menu

        :param modules.gui.main_ui.KnechtWindow ui:
        :param menu_name: name of the menu that will be displayed
        """
        super(AsSceneMenu, self).__init__(menu_name, ui)
        self.ui = ui

        self.addAction(self._no_conn_action())

        self.action_grp = QActionGroup(self)
        self.action_grp.setExclusive(True)

        self.setIcon(IconRsc.get_icon('paperplane'))
        self.aboutToShow.connect(self._about_to_show)

        QTimer.singleShot(500, self._delayed_setup)

    def _delayed_setup(self):
        self.ui.app.send_dg.plm_xml_controller.scene_active_result.connect(self._update_menu)
        self.ui.app.send_dg.plm_xml_controller.no_connection.connect(self._update_menu)

    def _update_menu(self, active_scene=None, scenes=None):
        self._clear_menu()

        if not active_scene and not scenes:
            self.addAction(self._no_conn_action())
            return

        for scene_name in scenes:
            self.create_scene_action(scene_name, scene_name == active_scene)

    def _warn_msg(self):
        return QAction(IconRsc.get_icon('warn'), _('AsConnector unterstützt nur Schaltungen in zuletzt geladener '
                                                   'Szene! Diese Funktion ist experimentell.'), self)

    def _no_conn_action(self):
        return QAction(IconRsc.get_icon('close'), _('Keine AsConnector Verbindung oder keine Szenen geöffnet.'), self)

    def _requested_info(self):
        return QAction(IconRsc.get_icon('later'), _('AsConnector Szenen angefordert, einen Moment.'), self)

    def _toggle_scene(self):
        for s in self.actions():
            if s.isChecked():
                scene_name = s.text()
                self.ui.app.send_dg.send_active_scene_request(scene_name)

    def create_scene_action(self, scene_name: str, is_active: bool):
        s = QAction(IconRsc.get_icon('document'), scene_name, self.action_grp)
        s.setCheckable(True)
        s.setChecked(is_active)
        s.triggered.connect(self._toggle_scene)

        self.addAction(s)

    def _clear_menu(self):
        self.clear()
        self.addAction(self._warn_msg())

    def _about_to_show(self):
        self._clear_menu()
        self.addAction(self._requested_info())

        # Request list of available AsConnector scene without setting a scene active(None)
        self.ui.app.send_dg.send_active_scene_request(None)

