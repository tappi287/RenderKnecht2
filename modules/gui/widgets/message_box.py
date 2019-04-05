from pathlib import Path

from PySide2.QtCore import Qt
from PySide2.QtWidgets import QMessageBox

from modules.gui.ui_resource import IconRsc
from modules.language import get_translation

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


def get_msg_box_icon(icon_key):
    if not icon_key:
        return IconRsc.get_icon('RK_Icon')
    else:
        return IconRsc.get_icon(icon_key)


class GenericMsgBox(QMessageBox):
    def __init__(self, parent, title: str = 'Message Box', text: str = 'Message Box.', icon_key=None, *__args):
        super(GenericMsgBox, self).__init__()
        self.parent = parent

        self.setWindowIcon(get_msg_box_icon(icon_key))

        self.setWindowTitle(title)
        self.setText(text)


class GenericErrorBox(GenericMsgBox):
    title = _('Fehler')
    txt = _('Allgemeiner Fehler')
    icon_key = 'RK_Icon'

    def __init__(self, parent):
        super(GenericErrorBox, self).__init__(parent, self.title, self.txt, self.icon_key)
        self.setIcon(QMessageBox.Warning)

    def set_error_msg(self, error_msg: str):
        self.setInformativeText(error_msg)


class XmlFailedMsgBox(GenericMsgBox):
    title = _('Xml Dokument')
    txt = _('Fehler beim Bearbeiten des Xml Dokuments.')
    icon_key = 'folder'

    def __init__(self, parent):
        super(XmlFailedMsgBox, self).__init__(parent, self.title, self.txt, self.icon_key)
        self.setIcon(QMessageBox.Warning)

    def set_error_msg(self, error_msg: str, file: Path):
        error_msg = _('{}<br><br>'
                      '<b>Datei:</b> <i>{}</i><br>'
                      '<b>Pfad:</b> <i>{}</i>'
                      '').format(error_msg, file.name, file.parent.as_posix())
        self.setInformativeText(error_msg)


class AskToContinue(GenericMsgBox):
    title = _('Aktion wirklich fortführen?')

    txt = _('Soll diese Aktion wirklich ausgeführt werden?')

    continue_txt = _('Fortfahren')
    abort_txt = _('Abbrechen')

    icon_key = 'RK_Icon'

    def __init__(self, parent):
        super(AskToContinue, self).__init__(parent, self.title, self.txt, self.icon_key)
        self.setIcon(QMessageBox.Question)
        self.setStandardButtons(QMessageBox.Ok | QMessageBox.Abort)

        self.setDefaultButton(QMessageBox.Ok)

    def ask(self, title: str='', txt: str='', ok_btn_txt: str='', abort_btn_txt: str=''):
        if title:
            self.setWindowTitle(title)
        if txt:
            self.setText(txt)

        ok_btn_txt = ok_btn_txt or self.continue_txt
        abort_btn_txt = abort_btn_txt or self.abort_txt

        self.button(QMessageBox.Ok).setText(ok_btn_txt)
        self.button(QMessageBox.Ok).setIcon(IconRsc.get_icon('play'))
        self.button(QMessageBox.Ok).setStyleSheet('padding: 4px 6px;')
        self.button(QMessageBox.Abort).setText(abort_btn_txt)
        self.button(QMessageBox.Abort).setIcon(IconRsc.get_icon('stop'))
        self.button(QMessageBox.Abort).setStyleSheet('padding: 4px 6px;')

        if self.exec_() == QMessageBox.Ok:
            return True
        return False


class AskToContinueCritical(AskToContinue):
    def __init__(self, parent):
        super(AskToContinueCritical, self).__init__(parent)
        self.setIcon(QMessageBox.Critical)
