import queue
from typing import Iterable

from PySide2 import QtWidgets
from PySide2.QtCore import QAbstractAnimation, QEasingCurve, QEvent, QPropertyAnimation, QRect, QTimer, QSize, Qt, Signal
from PySide2.QtGui import QEnterEvent, QFont, QMovie, QPalette, QShowEvent, QHideEvent, QMouseEvent, QFontMetrics

from modules.gui.ui_resource import FontRsc
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class _OverlayWidget(QtWidgets.QWidget):
    # Overlay specific font to correctly calculate font metrics
    # which do not get updated when widget font style or size changes
    overlay_font = FontRsc.get_font('SourceSansPro-Regular')

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

        self.header_height = 0

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


class InfoOverlay(_OverlayWidget):
    """ Provides an overlay area with additional information """
    # Signal that new message will be displayed
    # Curently only in use for MainWindowOverlay Resize Event
    new_message = Signal()

    # Overlay queue size
    queue_size = 8

    # Maximum message length
    max_length = 1500

    # Geometry
    offset_factor_y = 0.10
    overlay_width_factor = 0.65
    overlay_height = 42

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

        # Parent widget where overlay will be displayed
        self.parent: QtWidgets.QWidget = parent

        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setFocusPolicy(Qt.NoFocus)
        self.setStyleSheet('background: rgba(200,0,0,150);')

        if hasattr(self.parent, 'verticalScrollBar'):
            self.vertical_scroll_bar = self.parent.verticalScrollBar()
        else:
            self.vertical_scroll_bar = QtWidgets.QScrollBar(self)
            self.vertical_scroll_bar.hide()

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
        self.setLayout(self.box_layout)

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
        self.update_label_style(self.opacity)
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
        self.display_timer.timeout.connect(self.display_time_expired)

        self.mouse_leave_timer = QTimer()
        self.mouse_leave_timer.setSingleShot(True)
        self.mouse_leave_timer.setInterval(200)
        # Restore opacity after overlay was made transparent by mouse enter event
        self.mouse_leave_timer.timeout.connect(self.restore_visibility)

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

    def delayed_setup(self):
        font_size = 'font-size: {}px;'.format(int(round(FontRsc.regular.pixelSize() * 1.1)))
        self.text_style = self.text_style + ' ' + font_size
        # LOGGER.debug('Preparing text style: %s', self.text_style)
        self.update_label_style(self.opacity)

        self.txt_label.setMinimumWidth(405)
        self.txt_label.setMinimumHeight(self.overlay_height)
        self.txt_label.setMaximumWidth(int(self.parent.width() * self.overlay_width_factor))
        self.custom_resize()

    def _parent_resize_wrapper(self, event):
        self.org_parent_resize_event(event)
        self.custom_resize()

        event.accept()

    def eventFilter(self, obj, event):
        """ Make Widget transparent on Mouse Move and Enter Event """
        if obj is self.txt_label:
            # --- Detect Mouse Events ---
            if event.type() == QEnterEvent.Enter or event.type() == QMouseEvent.MouseMove:
                self.mouse_leave_timer.stop()
                self.update_label_style(40)
                event.accept()
                return True

            if event.type() == QEnterEvent.Leave:
                self.mouse_leave_timer.start()
                event.accept()
                return True

            if event.type() == QMouseEvent.MouseButtonPress and not self.btn_box.active:
                self.display_exit()
                event.accept()
                return True

        return False

    def restore_visibility(self):
        """ Restore opacity after mouse events """
        self.update_label_style(255)

    def update_label_style(self, opacity, right: int=5):
        bgr_style = self.bg_style.format(opacity=opacity) + self.text_style.format(opacity=opacity)
        bgr_style += f'padding-right: {right}px;'
        self.txt_label.setStyleSheet(bgr_style)

    def setup_timers(self):
        # Timer connections
        self.display_timer.timeout.connect(self.display_time_expired)

        # Restore opacity after overlay was made transparent by mouse enter event
        self.mouse_leave_timer.timeout.connect(self.restore_visibility)

    def display(self,
                message: str = 'Information overlay',
                duration: int = display_duration,
                immediate: bool = False,
                buttons: Iterable = tuple()):
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
                        buttons: Iterable = tuple(),
                        immediate: bool = False):
        """ Add overlay message and buttons and wait for confirmation """
        self.display(message, self.display_duration, immediate, buttons)

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
                    self.create_button(btn)

            # Display message
            self.txt_label.setText(message)
            self.new_message.emit()
            self.update_opacity(self.opacity, show_anim=show_anim)
            self.display_timer.start(duration)

    def create_button(self, button):
        """ Dynamic button creation on request """
        txt, callback = button

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
            # Resize on first show to adapt for button box size
            self.custom_resize()
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

        geo = self.custom_resize()
        start_x = geo.x() + geo.width() * end_val
        end_x = geo.x() + geo.width() * start_val

        start_rect = QRect(start_x, geo.y(), geo.width(), geo.height())
        end_rect = QRect(end_x, geo.y(), geo.width(), geo.height())

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

    def custom_resize(self):
        p = self.parent.frameGeometry()

        # Extra width from vertical scrollbar and btn box
        scrollbar_width, btn_width = 0, 0
        if self.vertical_scroll_bar.isVisible():
            scrollbar_width = self.vertical_scroll_bar.width()
        if self.btn_box.active:
            btn_width = self.btn_box.frameGeometry().width()

        # Set right padding required for scrollbar and btn_box
        self.update_label_style(self.opacity, (btn_width + scrollbar_width) or 5)

        # Width based on text size
        text_size = self.txt_label.fontMetrics().boundingRect(self.txt_label.text())
        # Limit to parent widget width
        w = min(p.width(), round((p.width() * self.overlay_width_factor)))
        # Set offset x position to align right
        x = p.width() - w
        # Set offset y position
        y = round(p.height() * self.offset_factor_y)
        # Height based on required lines of text
        # (FontMetrics will always return width for one line in this setup)
        extra_lines = int(text_size.width() / w) or 1
        h = round(self.txt_label.sizeHint().height() + (text_size.height() * extra_lines))

        self.txt_label.setMinimumWidth(w)
        self.setGeometry(x, y, w, h)

        return self.geometry()

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
