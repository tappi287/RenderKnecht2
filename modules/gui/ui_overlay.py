import queue

from PySide2 import QtWidgets
from PySide2.QtCore import QAbstractAnimation, QEasingCurve, QEvent, QPropertyAnimation, QRect, QTimer, QSize, Qt, Signal
from PySide2.QtGui import QEnterEvent, QFont, QMovie, QPalette, QShowEvent, QHideEvent, QMouseEvent

from modules.gui.ui_resource import FontRsc
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class _OverlayWidget(QtWidgets.QWidget):
    def __init__(self, parent):
        super(_OverlayWidget, self).__init__(parent)

        # Parent QWidget
        self.parent: QtWidgets.QWidget = parent
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

        try:
            height = parent.frameGeometry().height() + parent.header().height()
        except AttributeError:
            LOGGER.error('Overlay Parent has no attribute "header". Using frame height.')
            # Parent has no header
            height = parent.frameGeometry().height()

        # Add the QMovie object to the label
        self.movie_screen = QtWidgets.QLabel(self)
        self.movie_screen.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                        QtWidgets.QSizePolicy.Expanding)
        self.movie_screen.hide()

        # Install parent resize wrapper
        self.org_parent_resize_event = self.parent.resizeEvent
        self.parent.resizeEvent = self._parent_resize_wrapper

        QTimer.singleShot(1, self.first_size)

    def first_size(self):
        """ PySide2 seems not to guarantee a resize event before first show event """
        height = self.parent.frameGeometry().height() - self.header_height
        self.setGeometry(0, 0, self.parent.frameGeometry().width(), height)

    def _parent_resize_wrapper(self, event):
        self.org_parent_resize_event(event)
        self.resize(self.parent.size())

        event.accept()

    def move_to_center(self, current_mov):
        """ Move Screen to center """
        mr = current_mov.currentPixmap().rect()
        w, h = mr.width(), mr.height()

        r = self.parent.rect()
        x, y = r.width() / 2, r.height() / 2

        x, y = x - (w / 2), y - (h / 2)

        self.movie_screen.setGeometry(x, y, w, h)
        self._updateParent()

    def generic_center(self):
        """ Moves Movie to Center of parent """
        w, h = 64, 64
        r = self.parent.rect()
        x, y = r.width() / 2, r.height() / 2

        x, y = x - (w / 2), y - (h / 2)
        self.movie_screen.setGeometry(x, y, w, h)
        self._updateParent()

    def update_position(self, pos):
        """ Receives position of drop events """
        self.movie_screen.setGeometry(pos.x() - 32, pos.y(), 64, 64)
        self._updateParent()

    def _updateParent(self):
        """ Resize self and update parent widget """
        original = self.parent.resizeEvent

        def resizeEventWrapper(event):
            original(event)
            self.resize(event.size())

        resizeEventWrapper._original = original
        self.parent.resizeEvent = resizeEventWrapper
        self.resize(self.parent.size())


class Overlay(_OverlayWidget):
    """ Draw animated icons at cursor position to indicate user actions like copy etc. """

    def __init__(self, parent):
        super(Overlay, self).__init__(parent)

        self.parent = parent

        # Setup overlay movies
        # ref_created, copy_created
        movies = [
            # 0
            ':/anim/link_animation.gif',
            # 1
            ':/anim/copy_animation.gif',
            # 2
            ':/anim/coffee_animation.gif',
            # 3
            ':/anim/save_animation.gif',
        ]
        self.mov = []

        for i, m in enumerate(movies):
            self.mov.append(QMovie(m))
            self.mov[i].setCacheMode(QMovie.CacheAll)
            self.mov[i].setSpeed(100)
            self.mov[i].finished.connect(self.movie_finished)

        self.movie_screen.setMovie(self.mov[0])
        self.movie_screen.setGeometry(5, 20, 64, 64)

        self.show()

    def ref_created(self):
        """ Visual indicator for reference created """
        self.movie_screen.setMovie(self.mov[0])
        self.movie_screen.show()
        self.mov[0].jumpToFrame(0)
        self.mov[0].start()

    def copy_created(self):
        """ Visual indicator for copy created """
        self.movie_screen.setMovie(self.mov[1])
        self.movie_screen.show()
        self.mov[1].jumpToFrame(0)
        self.mov[1].start()

    def load_start(self):
        """ Visual indicator for load operation """
        self.movie_screen.setMovie(self.mov[2])
        self.mov[2].jumpToFrame(0)

        self.move_to_center(self.mov[2])
        self.movie_screen.show()

        self.mov[2].start()

    def load_finished(self):
        self.movie_screen.hide()
        self.mov[2].stop()

    def save_anim(self):
        """ Visual indicator for save operation """
        self.movie_screen.setMovie(self.mov[3])
        self.mov[3].jumpToFrame(0)
        self.movie_screen.show()

        self.move_to_center(self.mov[3])
        self.mov[3].start()

    def movie_finished(self):
        self.movie_screen.hide()


class IntroOverlay(_OverlayWidget):
    opaque_timer = QTimer()
    opaque_timer.setSingleShot(True)

    finished_signal = Signal()

    def __init__(self, parent):
        super(IntroOverlay, self).__init__(parent)
        self.parent = parent

        self.intro_mov = QMovie(':/anim/Introduction.gif')
        self.intro_mov.setCacheMode(QMovie.CacheAll)
        self.intro_mov.finished.connect(self.finished)
        self.opaque_timer.timeout.connect(self.set_opaque_for_mouse_events)

        self.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is None or event is None:
            return False

        if obj is self:
            if event.type() == QEvent.MouseButtonPress:
                self.mouse_click()
                return True

        return False

    def set_opaque_for_mouse_events(self):
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)

    def intro(self):
        LOGGER.info('Playing introduction in %sx %sy %spx %spx',
                    self.parent.rect().x(), self.parent.rect().y(),
                    self.parent.rect().width(), self.parent.rect().height())

        self.movie_screen.setMovie(self.intro_mov)
        self.movie_screen.setGeometry(self.parent.rect())
        self._updateParent()
        self.opaque_timer.start(1000)
        self.movie_screen.show()
        self.show()

        self.intro_mov.jumpToFrame(0)
        self.intro_mov.start()

    def mouse_click(self):
        self.intro_mov.stop()
        self.finished()

    def finished(self):
        self.movie_screen.hide()
        self.hide()
        self.finished_signal.emit()


class InfoOverlay(_OverlayWidget):
    """ Provides an overlay area with additional information """
    # Signal that new message will be displayed
    # Curently only in use for MainWindowOverlay Resize Event
    new_message = Signal()

    # Overlay queue size
    queue_size = 8

    # Maximum message length
    max_length = 1500

    # Mouse Timer
    mouse_leave_timer = QTimer()
    mouse_leave_timer.setSingleShot(True)
    mouse_leave_timer.setInterval(200)

    # Geometry
    offset_factor_y = 0.10
    overlay_width_factor = 0.65
    overlay_height = 36

    # Background appearance
    # will be rgba(0, 0, 0, opacity * bg_opacity)
    bg_opacity = 0.85  # Multiplier
    bg_style = 'background: rgba(50, 50, 50, {opacity:.0f});'

    # Text appearance
    # will be rgba(0, 0, 0, opacity)
    text_style = 'padding: 5px; color: rgba(211, 215, 209, {opacity});'

    # Default display duration
    display_duration = 800

    # Default opacity
    opacity = 255

    # Text Label Minimum Height
    lbl_min_height = 34

    def __init__(self, parent):
        super(InfoOverlay, self).__init__(parent)
        # TODO: disappears on tab change

        # Parent widget where overlay will be displayed
        self.parent: QtWidgets.QWidget = parent

        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setFocusPolicy(Qt.NoFocus)

        try:
            self.scroll_bar = self.parent.horizontalScrollBar()
            self.scroll_bar.installEventFilter(self)
        except Exception as e:
            LOGGER.error('Overlay parent has no horizontal scrollbar. %s', e)
            self.scroll_bar = QtWidgets.QScrollBar()

        # Disable horizontal scrollbar
        try:
            # self.widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            # Calc header margin
            self.header_height = self.parent.header().height()
        except Exception as e:
            LOGGER.info('Overlay widget has no scroll bar or header: %s', e)
            self.header_height = 0

        # Setup widget Layout
        self.box_layout = QtWidgets.QHBoxLayout(self)
        self.box_layout.setContentsMargins(0, self.header_height, 0, 0)
        self.box_layout.setSpacing(0)

        # Text Label
        self.txt_label = QtWidgets.QLabel(self)
        self.txt_label.setMouseTracking(True)
        self.txt_label.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.txt_label.setWordWrap(True)
        self.txt_label.setOpenExternalLinks(True)
        self.txt_label.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                     QtWidgets.QSizePolicy.Expanding)
        self.txt_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.txt_label.style_opacity = self.opacity
        self.txt_label.setStyleSheet(self.bg_style + self.text_style)
        self.label_animation = QPropertyAnimation(self, b"geometry")

        # Add Text Label to layout
        self.box_layout.addWidget(self.txt_label, 0, Qt.AlignLeft)

        # Button box
        self.btn_box = QtWidgets.QFrame(self)
        self.btn_box_layout = QtWidgets.QHBoxLayout(self.btn_box)
        self.btn_box_layout.setContentsMargins(11, 0, 33, 0)
        self.btn_box.setStyleSheet(self.bg_style)
        self.anim_btn = QPropertyAnimation(self.btn_box, b"geometry")

        # Add Button Box to layout
        self.box_layout.addWidget(self.btn_box, 0, Qt.AlignRight)
        self.btn_box.hide()

        # Button list
        self.btn_list = list()

        # Init timer's
        self.display_timer = QTimer()
        self.display_timer.setSingleShot(True)
        self.layout_timer = QTimer()
        self.layout_timer.setSingleShot(True)
        self.swap_timer = QTimer()
        self.swap_timer.setSingleShot(True)

        # Connect the timers
        self.setup_timers()

        # Create queue
        self.msg_q = queue.Queue(self.queue_size)

        # Dynamic properties
        self.txt_label.style_opacity = 0
        self.txt_label.duration = self.display_duration
        self.btn_box.active = False

        # Resize with every display message
        self.new_message.connect(self.custom_resize)

        # Move layout if widget entered by mouse
        self.txt_label.installEventFilter(self)
        self.txt_label.hide()

        # Hide initial overlay
        self.update_opacity(0, True)

        # Toggle a resize after first window draw
        QTimer.singleShot(1, self.delayed_setup)

    def _parent_resize_wrapper(self, event):
        self.org_parent_resize_event(event)
        self.custom_resize()

        event.accept()

    def delayed_setup(self):
        font_size = 'font-size: {}px;'.format(int(round(FontRsc.regular.pixelSize() * 1.1)))
        self.text_style = self.text_style + ' ' + font_size
        LOGGER.debug('Preparing text style: %s', self.text_style)
        bgr_style = self.bg_style + self.text_style
        self.txt_label.setStyleSheet(bgr_style)

        self.txt_label.setMinimumWidth(405)
        self.txt_label.setMaximumWidth(int(self.parent.width() * self.overlay_width_factor))
        self.custom_resize()

    def eventFilter(self, obj, event):
        """ Make Widget transparent on Mouse Move and Enter Event """
        if obj is self.txt_label:
            # --- Hide and restore overlay widget on label hide/show events ---
            if event.type() in [QEvent.Type.Show, QEvent.Type.ShowToParent, QShowEvent]:
                self.show()
            elif event.type() in [QEvent.Type.Hide, QEvent.Type.HideToParent, QHideEvent]:
                self.hide()

            # --- Detect Mouse Events ---
            if event.type() == QEnterEvent.Enter or event.type() == QMouseEvent.MouseMove:
                self.mouse_leave_timer.stop()
                self.update_label_opacity(40)
                event.accept()
                return True

            if event.type() == QEnterEvent.Leave:
                self.mouse_leave_timer.start()
                event.accept()
                return True

            if event.type() == QMouseEvent.MouseButtonPress:
                self.display_exit()
                event.accept()
                return True

        return False

    def restore_visibility(self):
        """ Restore opacity after mouse events """
        self.update_label_opacity(255)

    def update_label_opacity(self, opacity):
        bgr_style = self.bg_style.format(opacity=opacity) + self.text_style.format(opacity=opacity)
        self.txt_label.setStyleSheet(bgr_style)

    def setup_timers(self):
        # Timer connections
        self.display_timer.timeout.connect(self.display_time_expired)

        # Restore opacity after overlay was made transparent by mouse enter event
        self.mouse_leave_timer.timeout.connect(self.restore_visibility)

    def scroll_bar_eventFilter(self, obj, event):
        if obj is self.scroll_bar:
            if event.type() == QEvent.Type.Hide:
                LOGGER.debug('Scroll Bar Hidden - Re-setting Overlay Size')
                self.txt_label.setMinimumHeight(self.lbl_min_height)

                LOGGER.debug('Label Size Hint: %s, Actual Size: %s', self.txt_label.minimumSizeHint().height(),
                             self.txt_label.size().height())
                return True
            elif event.type() == QEvent.Type.Show:
                LOGGER.debug('Scroll Bar Shown - Resizing Overlay')
                self.txt_label.setMinimumHeight(self.lbl_min_height)
                self.txt_label.setMinimumHeight(round(self.lbl_min_height + self.scroll_bar.height() * 1.5))

                LOGGER.debug('Label Size Hint: %s, Actual Size: %s', self.txt_label.minimumSizeHint().height(),
                             self.txt_label.size().height())
                return True

            return False

    def custom_resize(self):
        p = self.parent.frameGeometry()

        btn_width = self.btn_box.frameGeometry().width()

        # Set offset y position
        y = int(p.height() * self.offset_factor_y)

        # Size based on text size and limit Overlay Width factor
        max_width = int(p.width() * self.overlay_width_factor)
        text_size = self.txt_label.fontMetrics().boundingRect(self.txt_label.text())
        width = min(text_size.width(), max_width)
        self.txt_label.setMinimumWidth(width)

        # Align Right
        x = p.width() - width

        # Height
        h = self.txt_label.sizeHint().height()

        self.setGeometry(x, y, width, h)

    def display(self,
                message: str = 'Information overlay',
                duration: int = display_duration,
                immediate: bool = False,
                *buttons):
        """ add new overlay message """
        if self.msg_q.full():
            return

        # Single message
        self.msg_q.put((message, duration, buttons))

        if immediate:
            # Request immediate display by forcing a short timeout event
            self.stop_timer()

        if not self.display_timer.isActive():
            if not self.btn_box.active:
                self.display_next_entry()

    def display_confirm(self,
                        message: str = 'Confirm message',
                        *buttons,
                        immediate: bool = False) -> None:
        """ Add overlay message and buttons and wait for confirmation """
        self.display(message, self.display_duration, immediate, *buttons)

    def display_time_expired(self, was_btn_box=False):
        if self.msg_q.empty():
            if was_btn_box:
                self.update_opacity(0)
            else:
                self.update_opacity(0, show_anim=True)
            return

        if not self.btn_box.active:
            self.display_next_entry()

    def clear(self):
        """ Clear overlay messages """
        self.display_exit()

    def display_exit(self):
        """ Exit confirmation dialog with buttons """
        self.btn_box.active = False

        # Delete buttons
        if self.btn_list:
            for btn in self.btn_list:
                btn.deleteLater()

            self.btn_list = list()

        # Hide overlay
        self.display_time_expired(was_btn_box=True)

    def display_next_entry(self):
        """ Get next message from queue, check lenght and display it """
        q = self.msg_q.get()

        if q is not None:
            # Unpack tuple
            message, duration, buttons = q

            # Display animation on initial display event
            show_anim = False
            if self.txt_label.style_opacity == 0:
                show_anim = True

            # Create Buttons
            if buttons:
                for btn in buttons:
                    self.create_button(*btn)

            # Display message
            self.txt_label.setText(message)
            self.new_message.emit()
            self.update_opacity(self.opacity, show_anim=show_anim)
            self.display_timer.start(duration)

    def create_button(self, txt: str = 'Button', callback=None):
        """ Dynamic button creation on request """
        new_button = QtWidgets.QPushButton(txt, self.btn_box)
        new_button.setStyleSheet('background-color: white;')
        self.btn_box_layout.addWidget(new_button, 0, Qt.AlignRight)

        if callback is None:
            new_button.pressed.connect(self.display_exit)
        else:
            new_button.pressed.connect(callback)

        self.btn_box.active = True
        self.btn_list.append(new_button)

    def update_opacity(self, opacity: int, show_anim: bool=True):
        """ called from worker thread for animated fade out """
        # Do not hide widget if Confirmation question displayed
        if self.btn_box.active:
            opacity = self.opacity
            self.btn_box.show()

            self.label_animation.stop()
            show_anim=False
        else:
            self.btn_box.hide()

        self.txt_label.style_opacity = opacity

        if self.txt_label.style_opacity >= 1:
            self.txt_label.show()

            if show_anim:
                self.init_animation(0, 1, 90)
        else:
            if show_anim:
                self.init_animation(1, 0, 600)
            else:
                self.txt_label.hide()

    def init_animation(self, start_val, end_val, duration):
        if self.label_animation.state() == QAbstractAnimation.Running:
            if end_val > 0:
                self.label_animation.stop()
            return

        self.custom_resize()
        y = int(self.parent.frameGeometry().height() * self.offset_factor_y)
        h = self.height()
        w = self.width()
        x = self.parent.frameGeometry().width() - w

        start_x = x + w * end_val
        end_x = x + w * start_val

        start_rect = QRect(start_x, y, w, h)
        end_rect = QRect(end_x, y, w, h)

        self.label_animation.setDuration(duration)
        self.label_animation.setStartValue(start_rect)
        self.label_animation.setEndValue(end_rect)

        if end_val > 0:
            # Show Widget Easing
            self.label_animation.setEasingCurve(QEasingCurve.InCubic)
        else:
            # Hide Widget Easing
            self.label_animation.setEasingCurve(QEasingCurve.InExpo)

        self.label_animation.start(QPropertyAnimation.KeepWhenStopped)

        self.label_animation.finished.connect(self.anim_label_finished)

    def anim_label_finished(self):
        if self.txt_label.style_opacity == 0:
            self.txt_label.hide()

    def stop_timer(self):
        """ Restart timer with short timeout if it is currently active """
        if self.display_timer.isActive():
            self.display_timer.start(20)


class MainWindowOverlay(InfoOverlay):
    offset_factor_y = 0.10
    overlay_width_factor = 0.65
    overlay_height = 36

    bg_opacity = 0.90  # Multiplier
    bg_style = 'background: rgba(40, 40, 40, {opacity:.0f});'

    def __init__(self, parent):
        super(MainWindowOverlay, self).__init__(parent)
        # Restore opacity after overlay was made transparent by mouse enter event
        self.mouse_leave_timer.timeout.connect(self.restore_visibility)

        # Install main Window Event Filter
        self.txt_label.installEventFilter(self)
