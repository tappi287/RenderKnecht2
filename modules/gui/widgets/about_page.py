import sys

from PySide2.QtWidgets import QWidget

from modules.globals import Resource, FROZEN
from modules.gui.gui_utils import SetupWidget
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


GNU_MESSAGE = 'RenderKnecht is free software: you can redistribute it and/or modify<br>' \
              'it under the terms of the GNU General Public License as published by<br>' \
              'the Free Software Foundation, either version 3 of the License, or<br>' \
              '(at your option) any later version.<br><br>' \
              'RenderKnecht is distributed in the hope that it will be useful,<br>' \
              'but WITHOUT ANY WARRANTY; without even the implied warranty of<br>' \
              'MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the<br>' \
              'GNU General Public License for more details.<br><br>' \
              'You should have received a copy of the GNU General Public License<br>' \
              'along with RenderKnecht. If not, see <a href="http://www.gnu.org/licenses/">here.</a>'


class InfoMessage:
    START_INFO = 'Python %s Platform %s' % (sys.version, sys.platform)
    ENV = ''
    ver = ''
    lic = ''
    auth = ''
    mail = ''
    cred = ''
    stat = ''
    icon_credits = (
        (":/type/pkg.png", "Box", "by Gregor Cresnar", "http://www.flaticon.com/", "Flaticon Basic License"),
        (":/type/checkmark.png", "Checkmark", "by Freepik", "http://www.flaticon.com/", "Flaticon Basic License"),
        (":/type/fakom.png", "Leather", "by Smashicons", "http://www.flaticon.com/", "Flaticon Basic License"),
        (":/main/dog.png", "Dog", "by Twitter", "http://www.flaticon.com/", "CC 3.0 BY"),
        (":/type/car.png", "Car front", "by Google", "http://www.flaticon.com/", "CC 3.0 BY"),
        (":/type/img.png", "Google Drive image", "by Google", "http://www.flaticon.com/", "CC 3.0 BY"),
        (":/type/preset.png", "Gear black shape", "by SimpleIcon", "http://www.flaticon.com/", "CC 3.0 BY"),
        (":/type/options.png", "Listing option", "by Dave Gandy", "http://www.flaticon.com/", "CC 3.0 BY"),
        (":/type/reset.png", "Reload Arrow", "by Plainicon", "http://www.flaticon.com/", "CC 3.0 BY"),
        (":/main/paint.png", "color-palette", "by Ionicons", "https://ionicons.com/", "MIT License"),
        (":/main/forward.png", "forward", "by Ionic", "http://ionicframework.com/", "MIT License"),
        (":/main/sad.png", "sad", "by Ionic", "http://ionicframework.com/", "MIT License"),
        (":/main/eye-disabled.png", "eye-disabled", "by Ionic", "http://ionicframework.com/", "MIT License"),
        (":/main/log-in.png", "log-in", "by Ionic", "http://ionicframework.com/", "MIT License"),
        (":/main/navicon.png", "navicon", "by Ionic", "http://ionicframework.com/", "MIT License"),
        (":/main/social-github.png", "social-github", "by Ionic", "http://ionicframework.com/", "MIT License"),
        (":/main/update.png", "Other icons by Material.io", "by Google", "https://material.io", "Apache License 2.0"),
    )
    license_links = {"CC 3.0 BY": "https://creativecommons.org/licenses/by/3.0/",
                     "MIT License": "https://opensource.org/licenses/MIT",
                     "Flaticon Basic License": "http://www.flaticon.com/",
                     "Apache License 2.0": "http://www.apache.org/licenses/",}

    @classmethod
    def get(cls):
        if FROZEN:
            cls.ENV = 'Running frozen in bundled interpreter.'
        else:
            cls.ENV = 'Running unfrozen in IDE.'

        info_msg = ['<b>RenderKnecht</b> v{version} licensed under {license}'
                    .format(version=cls.ver, license=cls.lic),
                    '(c) Copyright 2017-2019 {author}<br>'
                    '<a href="mailto:{mail}" style="color: #363636">{mail}</a>'
                    '<p style="font-family: Inconsolata;vertcial-align: middle;margin: 20px 0px 28px 0px">'
                    '<a href="https://github.com/tappi287/RenderKnecht2" style="color: #363636">'
                    '<img src=":/main/social-github.png" width="24" height="24" '
                    'style="float: left;vertical-align: middle;">'
                    'Visit RenderKnecht source on Github</a>'
                    '<br>{system}; {env}'
                    '</p>'
                    '<h4>Credits:</h4><b>{credits}</b>'
                    '<h4>Resource Credits:</h4>{icon_credits}'
                    '<h4>Information:</h4>'
                    '<p style="font-size: 10pt;"><i>{gnu}</i></p><br>'
                    .format(author=cls.auth,
                            mail=cls.mail,
                            credits=cls.credit_list(),
                            system=cls.START_INFO,
                            icon_credits=cls.resource_credits(),
                            status=cls.stat,
                            env=cls.ENV,
                            gnu=GNU_MESSAGE)]

        return info_msg

    @classmethod
    def credit_list(cls):
        html_lines = ''
        for line in cls.cred:
            html_lines += f'<li>{line}</li>'

        return f'<ul style="list-style-type: none;">{html_lines}</ul>'

    @classmethod
    def resource_credits(cls):
        icon_credits = cls.icon_credits
        license_links = cls.license_links
        html_lines = ''

        # Add icon credits
        for line in icon_credits:
            icon_path, name, author, author_link, lic = line
            # f'<img src="{icon_path}" width="18" height="18" style="float: left;">' \

            html_lines += f'<li>' \
                          f'<span style="font-size: 10pt;">' \
                          f'<img src="{icon_path}" width="24" height="24" ' \
                          f'style="vertical-align: baseline; display: inline"> ' \
                          f'"{name}" <b><a style="color: #363636" href="{author_link}">{author}</a></b> ' \
                          f'licensed under <a style="color: #363636" href="{license_links[lic]}">{lic}</a>' \
                          f'</span>' \
                          f'</li>'

        # Add font credit line
        html_lines += '<li style="line-height: 28px; font-family: Inconsolata"><span style="font-size: 10pt;">' \
                      'Inconsolata Font by ' \
                      '<b><a href="http://levien.com/type/myfonts/inconsolata.html" style="color: #363636">' \
                      'Raph Levien</a></b> ' \
                      '<a style="color: #363636" href="http://scripts.sil.org/OFL">' \
                      'SIL Open Font License, Version 1.1</a>' \
                      '</span></li>'

        # Add Source Sans Pro font credit line
        html_lines += '<li style="line-height: 28px;"><span style="font-size: 10pt;">' \
                      'Source Sans Pro Font by ' \
                      '<b><a href="https://fonts.google.com/specimen/Source+Sans+Pro" style="color: #363636">' \
                      'Paul D. Hunt</a></b> ' \
                      '<a style="color: #363636" href="http://scripts.sil.org/OFL">' \
                      'SIL Open Font License, Version 1.1</a>' \
                      '</span></li>'

        return f'<ul style="list-style-type: none;">{html_lines}</ul>'


class KnechtAbout(QWidget):

    def __init__(self, ui):
        """ Generic welcome page

        :param modules.gui.main_ui.KnechtWindow ui: Knecht main window
        """
        super(KnechtAbout, self).__init__()
        SetupWidget.from_ui_file(self, Resource.ui_paths['knecht_about'])
        self.ui = ui
        self.setWindowTitle(('Info'))

        self.title_label.setText('RenderKnecht v{}'.format(InfoMessage.ver))
        self.update_about_text()

    def update_about_text(self):
        msg = InfoMessage.get()
        headline, info_msg = msg[0], msg[1]

        self.headline_label.setText(headline)
        self.desc_label.setText(info_msg)
