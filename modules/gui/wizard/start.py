from PySide2.QtCore import QTimer
from PySide2.QtGui import QIcon
from PySide2.QtWidgets import QWizard, QWizardPage, QLabel

from modules.globals import Resource
from modules.gui.gui_utils import SetupWidget
from modules.gui.ui_resource import IconRsc
from modules.gui.widgets.expandable_widget import KnechtExpandableWidget
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class WelcomeWizardPage(QWizardPage):
    def __init__(self, wizard: QWizard):
        """ Wizard start page with session reload, save and package filter options.

        :param modules.gui.wizard.wizard.PresetWizard wizard: The parent wizard
        """
        super(WelcomeWizardPage, self).__init__()
        self.wizard = wizard
        SetupWidget.from_ui_file(self, Resource.ui_paths['wizard_start'])

        self.setTitle(_('Preset Wizard'))
        self.setSubTitle(_('Dieser Assistent führt durch die Erstellung von Presets aus Importdaten. '
                           'Gewünschte Modelle und Optionen können in nachfolgenden '
                           'Schritten gewählt werden.'))

        # -- Setup Page Ui --
        self.filter_box.setTitle(_('Landespaket Filter'))
        self.filter_icon.setPixmap(IconRsc.get_pixmap('pkg'))
        self.country_filter_desc.setText(_('Dieser Filter ermöglicht den Ausschluß meist unbenötigter und '
                                           'redundanter Pakete für einzelne, länderspezifische Märkte. '
                                           'Die gefilterten Pakete bleiben sicht- und zuweisbar. Sie werden aber '
                                           'als verwendet markiert so dass die automagische Zuweisung sie ignoriert.'))
        self.checkbox_country_filter.setText(_('Landesspezifische Pakete als verwendet markieren'))
        self.country_filter_expand_btn.setText(_('Filter anzeigen/bearbeiten'))
        arrow_icon = IconRsc.get_icon('arrow')
        arrow_icon.addPixmap(IconRsc.get_pixmap('arrow_up'), QIcon.Normal, QIcon.On)
        self.country_filter_expand_btn.setIcon(arrow_icon)
        self.load_btn.setStatusTip(_('Session aus Datei laden'))
        self.load_btn.setIcon(IconRsc.get_icon('folder'))
        self.save_btn.setStatusTip(_('Session in Datei sichern'))
        self.save_btn.setIcon(IconRsc.get_icon('disk'))
        self.restore_btn.setText(_('Letzte Sitzung wiederherstellen'))
        self.restore_btn.setIcon(IconRsc.get_icon('undo'))

        self.restore_btn.released.connect(self.wizard.restore_last_session)
        self.country_filter_expand_btn.released.connect(self.toggle_filter_edit)

    def initializePage(self):
        self.reload_pkg_filter()

    def toggle_filter_edit(self):
        if self.country_filter_text_edit.isVisible():
            self.country_filter_text_edit.hide()
        else:
            self.country_filter_text_edit.show()

    def reload_pkg_filter(self):
        # Prepare Filter Text Edit
        filter_string = ''
        for f in self.wizard.session.data.pkg_filter:
            filter_string += f'{f}; '
        self.country_filter_text_edit.setPlainText(filter_string)

    def read_pkg_filter(self):
        if not self.checkbox_country_filter.isChecked():
            return list()

        filter_string = self.country_filter_text_edit.toPlainText()
        filter_string = filter_string.replace('; ', ';').replace('\n', '')
        filter_string = filter_string.replace('\r', '').replace('\t', '')

        __filter_list = filter_string.split(';')

        for __s in ('', ' ', ' ;'):
            if __s in __filter_list:
                __filter_list.remove(__s)

        return __filter_list

    def validatePage(self):
        """ Set wizard data upon page exit """
        self.wizard.session.data.pkg_filter = self.read_pkg_filter()
        return True
