from PySide2.QtWidgets import QMenu, QAction, QActionGroup

from modules.settings import KnechtSettings
from modules.gui.ui_resource import FontRsc
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class ViewMenu(QMenu):
    font_size_setting = 0  # 0, 1, 2 Small, Standard, Big

    def __init__(self, ui, menu_name: str = _('Ansicht')):
        super(ViewMenu, self).__init__(menu_name, ui)
        self.ui = ui

        # --- App style ---
        self.addSeparator().setText(_('Anwendungs-Stil'))
        style_grp = QActionGroup(self)
        self.default_style = QAction(_('Standard'), style_grp)
        self.default_style.setCheckable(True)
        self.default_style.triggered.connect(self.switch_default_style)

        self.dark_style = QAction(_('Dunkel'), style_grp)
        self.dark_style.setCheckable(True)
        self.dark_style.triggered.connect(self.switch_dark_style)

        self.addActions([self.default_style, self.dark_style])

        # --- Font Size ---
        self.addSeparator().setText(_('Schrifgröße'))
        font_grp = QActionGroup(self)
        self.small_font = QAction(_('Klein'), font_grp)
        self.small_font.setCheckable(True)
        self.default_font = QAction(_('Standard'), font_grp)
        self.default_font.setCheckable(True)
        self.big_font = QAction(_('Groß'), font_grp)
        self.big_font.setCheckable(True)

        font_grp.triggered.connect(self.switch_font_size)
        self.addActions([self.small_font, self.default_font, self.big_font])

        self.display_current_style()

    def display_current_style(self):
        """ Set action checked according to KnechtSettings """

        if KnechtSettings.app.get('app_style') == 'fusion-dark':
            self.dark_style.setChecked(True)
        else:
            self.default_style.setChecked(True)

        if KnechtSettings.app['font_size'] == FontRsc.small_pixel_size:
            self.small_font.setChecked(True)
            self.font_size_setting = 0
        elif KnechtSettings.app['font_size'] == FontRsc.regular_pixel_size:
            self.default_font.setChecked(True)
            self.font_size_setting = 1
        elif KnechtSettings.app['font_size'] == FontRsc.big_pixel_size:
            self.big_font.setChecked(True)
            self.font_size_setting = 2

    def switch_default_style(self):
        self.ui.app.set_default_style()
        self.set_app_font(self.font_size_setting)

    def switch_dark_style(self):
        self.ui.app.set_dark_style()
        self.set_app_font(self.font_size_setting)

    def switch_font_size(self, action: QAction):
        action.setChecked(True)

        if action is self.small_font:
            self.set_app_font(0)
        elif action is self.default_font:
            self.set_app_font(1)
        elif action is self.big_font:
            self.set_app_font(2)

    def set_app_font(self, size: int=0):
        self.font_size_setting = size

        if size == 0:
            font_size = FontRsc.small_pixel_size
        elif size == 1:
            font_size = FontRsc.regular_pixel_size
        elif size == 2:
            font_size = FontRsc.big_pixel_size

        KnechtSettings.app['font_size'] = font_size

        self.ui.msg(_('Anwendungstil geändert. Für eine vollständige Übernahme muss die Anwendung neu gestartet '
                      'werden.'), 5000)

        FontRsc.init(font_size)
        self.ui.app.setFont(FontRsc.regular)
