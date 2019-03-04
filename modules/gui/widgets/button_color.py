from PySide2.QtCore import Signal, Qt, Slot
from PySide2.QtGui import QColor
from PySide2.QtWidgets import QPushButton, QColorDialog

from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class QColorButton(QPushButton):
    """
        Custom Qt Widget to show a chosen color.

        Left-clicking the button shows the color-chooser, while
        right-clicking resets the color to None (no-color).
    """

    colorChanged = Signal(QColor)
    style_id = 'QPushButton#pushButton_Bgr'
    bg_style = 'background-color: rgb(230, 230, 230);'
    border_style = 'border: 1px solid rgb(0, 0, 0);'

    def __init__(self, *args, **kwargs):
        super(QColorButton, self).__init__(*args, **kwargs)

        self._color = None
        self.set_color(QColor(255, 255, 255, 255))

        self.setMaximumWidth(32)
        self.pressed.connect(self.on_color_picker)

    def set_color_from_string(self, color: str):
        q_color = QColor(color)
        self.set_color(q_color)

    def set_color(self, color: QColor):
        self._color = color
        self.colorChanged.emit(color)

        if self._color:
            style = "{!s} {{background-color: {!s}; {!s}}}".format(
                     self.style_id, self._color.name(), self.border_style)
        else:
            style = "QPushButton#pushButton_Bgr {{{!s} {!s}}}".format(
                     self.style_id, self.bg_style, self.border_style)

        LOGGER.debug('Setting Style: %s', style)
        self.setStyleSheet(style)

    def color(self):
        return self._color

    @Slot()
    def on_color_picker(self):
        """ Show color-picker dialog to select color. Qt will use the native dialog by default. """
        dlg = QColorDialog(self)

        # We will need an RGBA color value
        dlg.setOption(QColorDialog.ShowAlphaChannel, True)
        dlg.setCurrentColor(self.color())

        dlg.finished.connect(self.dialog_finished)

        dlg.open()

    @Slot(int)
    def dialog_finished(self, result: int):
        dlg = self.sender()
        LOGGER.debug('Dialog result: %s %s', result, dlg.currentColor())

        if result == QColorDialog.Accepted:
            self.set_color(dlg.currentColor())

    def mousePressEvent(self, e):
        if e.button() == Qt.RightButton:
            self.set_color(QColor(255, 255, 255, 255))
            e.accept()

        return super(QColorButton, self).mousePressEvent(e)
