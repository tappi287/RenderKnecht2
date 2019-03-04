from PySide2 import QtWidgets, QtCore

from modules.gui.gui_utils import PredictProgressTime
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class ProgressOverlay(QtWidgets.QWidget):
    """ Displays a progress bar on top of the provided parent QWidget """
    progress_bar_width_factor = 0.5

    def __init__(self, parent):
        super(ProgressOverlay, self).__init__(parent)

        self.parent = parent
        self.setFocusPolicy(QtCore.Qt.NoFocus)

        try:
            self.header_height = self.parent.header().height()
        except AttributeError:
            self.header_height = 0

        # Make widget transparent
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)

        # Setup widget Layout
        self.box_layout = QtWidgets.QHBoxLayout(self.parent)
        self.box_layout.setContentsMargins(0, self.header_height, 0, 0)
        self.box_layout.setSpacing(0)

        self.progress = QtWidgets.QProgressBar(parent=self)
        self.progress.setFocusPolicy(QtCore.Qt.NoFocus)
        self.progress.setFormat('%v/%m')
        self.progress.setAlignment(QtCore.Qt.AlignCenter)
        self.progress.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        # Hide this widget if progress bar is hidden/shown
        self.progress.hideEvent = self._progress_show_hide_event_wrapper
        self.progress.showEvent = self._progress_show_hide_event_wrapper

        self.box_layout.addWidget(self.progress, 0, QtCore.Qt.AlignCenter)

        # Install parent resize wrapper
        self.org_parent_resize_event = self.parent.resizeEvent
        self.parent.resizeEvent = self._parent_resize_wrapper

        self.progress.hide()
        self.hide()

        QtCore.QTimer.singleShot(1, self.first_size)

    def first_size(self):
        """ PySide2 seems not to guarantee a resize event before first show event """
        height = self.parent.frameGeometry().height() - self.header_height
        self.setGeometry(0, 0, self.parent.frameGeometry().width(), height)
        self.progress.setMinimumWidth(round(self.width() * self.progress_bar_width_factor))

    def _progress_show_hide_event_wrapper(self, event):
        if event.type() == QtCore.QEvent.Hide:
            self.hide()
        elif event.type() == QtCore.QEvent.Show:
            self.show()

    def _parent_resize_wrapper(self, event):
        self.org_parent_resize_event(event)
        self.resize(self.parent.size())
        self.progress.setMinimumWidth(round(self.width() * self.progress_bar_width_factor))

        event.accept()


class ShowProgressSteps:
    progressBar = None
    initial_progress_format = str()

    def __init__(self, progress_bar: QtWidgets.QProgressBar, work_steps: int, step_size: int):
        """ Helper to display step wise progress in the progress overlay

            :param QtWidgets.QProgressBar: The progressBar to manipulate.

            :param int work_steps:  The maximum number of work steps that will be performed.
                                    Every step must call *update_progress* to present
                                    progress to the user. Or define a step_size after which
                                    you will call again.

            :param int step_size:   The number of steps that will be displayed as progressed
                                    until the next time you call *update_progress*.
        """
        self.progressBar = progress_bar

        self.initial_progress_format = self.progressBar.format()
        self.step_size = step_size
        self.work_steps = work_steps

        self.progressBar.setValue(0)
        self.progressBar.setMaximum(self.work_steps)
        self.progressBar.setFormat('%v/%m')
        self.progressBar.show()

        self.time_calc = PredictProgressTime(work_steps, step_size)

    def update_progress(self):
        value = min(self.work_steps, self.progressBar.value() + self.step_size)
        rem_time = self.time_calc.update()

        LOGGER.debug('{0:03d}/{1:03d} - Verbleibend: {2}'.format(value, self.work_steps, rem_time))
        """
        self.progressBar.setFormat(_('{0:03d}/{1:03d} - Verbleibend: {2}').format(
            value, self.work_steps, rem_time
            ))
        """
        self.progressBar.setValue(value)

    def finish_progress(self):
        self.progressBar.hide()
        self.progressBar.setFormat(self.initial_progress_format)


class ShowTreeViewProgressMessage(QtCore.QObject):
    progressBar = None
    initial_progress_format = str()

    def __init__(self, view, message: str=''):
        super(ShowTreeViewProgressMessage, self).__init__(view)
        self.view = view
        self.message = message

    def msg(self, message: str):
        self.message = message

    def get_progress_bar(self):
        try:
            self.progressBar = self.view.progress
        except AttributeError:
            self.progressBar = QtWidgets.QProgressBar(self)

        self.initial_progress_format = self.progressBar.format()
        self.progressBar.setFormat(self.message)

    def show_progress(self):
        self.get_progress_bar()

        if self.progressBar.isVisible():
            return

        self.progressBar.setValue(1)
        self.progressBar.setMaximum(1)
        self.progressBar.show()

    def hide_progress(self):
        self.message = ''
        self.progressBar.setFormat(self.initial_progress_format)
        self.progressBar.hide()
