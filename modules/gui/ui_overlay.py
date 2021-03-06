import re

from PySide2 import QtWidgets
from PySide2.QtCore import QAbstractAnimation, QPropertyAnimation, QTimer, Qt, QUrl
from PySide2.QtGui import QEnterEvent, QMouseEvent, QMovie, QRegion
from datetime import datetime

from modules.globals import Resource
from modules.gui.animation import BgrAnimation, TabBgrAnimation
from modules.gui.gui_utils import SetupWidget
from modules.gui.ui_resource import IconRsc
from modules.idgen import KnechtUuidGenerator
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class InfoOverlay(QtWidgets.QWidget):
    # Positioning
    y_offset_factor = 0.10
    x_offset_factor = 0.25

    # Default opacity
    txt_opacity = 255
    bg_opacity = 180
    bg_color = (30, 30, 30, bg_opacity)

    queue_limit = 12

    # Message tab index
    msg_tab_idx = 4

    def __init__(self, parent: QtWidgets.QWidget):
        super(InfoOverlay, self).__init__(parent)

        # --- These will be replaced from the ui file ---
        self.overlay_grp = QtWidgets.QWidget()
        self.top_space_widget = QtWidgets.QWidget()
        self.left_space_widget = QtWidgets.QWidget()
        self.btn_box = QtWidgets.QWidget()
        self.text_label = QtWidgets.QLabel()

        SetupWidget.from_ui_file(self, Resource.ui_paths['knecht_overlay'])

        # --- Init Attributes ---
        self.parent = parent
        self.queue = list()
        self.btn_list = list()
        self.message_active = False

        # -- Prepare Message Browser --
        self.msg_browser = QtWidgets.QTextBrowser()
        self.anchors = dict()
        self.msg_tab = QtWidgets.QTabWidget()
        self.tab_widget_anim = TabBgrAnimation(self)  # Animate MainWindow TabWidget Tab background color
        self.use_msg_browser = False

        # --- Get header height ---
        self.header_height = 0
        if hasattr(parent, 'header'):
            self.header_height = parent.header().height()

        # --- Setup Overlay Attributes ---
        self.style = 'background: rgba(' + f'{self.bg_color[0]}, {self.bg_color[1]}, {self.bg_color[2]},'\
                     + '{0}); color: rgba(233, 233, 233, {1});'
        self.bg_anim = BgrAnimation(self.overlay_grp, self.bg_color,
                                    additional_stylesheet=f'color: rgba(233, 233, 233, {self.txt_opacity});')

        self.restore_visibility()
        self.overlay_grp.installEventFilter(self)
        self.animation = QPropertyAnimation(self.overlay_grp, b"geometry")
        self.text_label.setOpenExternalLinks(True)

        # --- Init Timers ---
        self.msg_timer = QTimer()
        self.msg_timer.setSingleShot(True)
        self.msg_timer.timeout.connect(self._next_entry)

        self.mouse_leave_timer = QTimer()
        self.mouse_leave_timer.setSingleShot(True)
        self.mouse_leave_timer.setInterval(150)
        self.mouse_leave_timer.timeout.connect(self.restore_visibility)

        self.click_timer = QTimer()
        self.click_timer.setSingleShot(True)

        # --- Install parent resize wrapper ---
        self._org_parent_resize_event = self.parent.resizeEvent
        self.parent.resizeEvent = self._parent_resize_wrapper

        # --- Install Show Event wrapper ---
        # On document tab change, parent widget will not trigger resize event
        # but maybe was resized while hidden. This wrapper will make sure we adapt
        # size on tab change.
        self._org_parent_show_event = self.parent.showEvent
        self.parent.showEvent = self._parent_show_wrapper

        # Manually trigger an initial resize event
        QTimer.singleShot(1, self._adapt_size)

        self.hide_all()

    def eventFilter(self, obj, event):
        """ Make Widget transparent on Mouse Move and Enter Event """
        if obj in (self.overlay_grp, self.text_label, self.btn_box):
            # --- Detect Mouse Events ---
            if event.type() == QEnterEvent.Enter or event.type() == QMouseEvent.MouseMove:
                self.mouse_leave_timer.stop()
                self.set_opacity(30)
                event.accept()
                return True

            if event.type() == QEnterEvent.Leave:
                self.mouse_leave_timer.start()
                event.accept()
                return True

            if event.type() == QMouseEvent.MouseButtonPress and not self.btn_list and not self.click_timer.isActive():
                self.display_exit()
                event.accept()
                return True

        return False

    def _parent_resize_wrapper(self, event):
        self._org_parent_resize_event(event)
        self._adapt_size()
        event.accept()

    def _parent_show_wrapper(self, event):
        self._org_parent_show_event(event)
        self._adapt_size()
        event.accept()

    def _adapt_size(self):
        top_spacing = round(self.parent.frameGeometry().height() * self.y_offset_factor) + self.header_height
        left_spacing = round(self.parent.frameGeometry().width() * self.x_offset_factor)

        self.left_space_widget.setMinimumWidth(left_spacing)
        self.top_space_widget.setMinimumHeight(top_spacing)
        self.resize(self.parent.size())

        # Mask out invisible areas to -not- grab mouse events from that region
        reg = QRegion(self.parent.frameGeometry())
        reg -= self.frameGeometry()
        reg += self.overlay_grp.frameGeometry()
        self.setMask(reg)

    def setup_message_browser(self, message_browser: QtWidgets.QTextBrowser, ui_tab_widget: QtWidgets.QTabWidget):
        self.tab_widget_anim = TabBgrAnimation(ui_tab_widget)
        self.msg_tab = ui_tab_widget
        self.msg_browser = message_browser
        self.msg_browser.anchorClicked.connect(self._msg_browser_anchor_clicked)
        self.use_msg_browser = True

    def _msg_browser_anchor_clicked(self, url: QUrl):
        anchor_id = url.toDisplayString()[1:]

        if anchor_id in self.anchors:
            callback = self.anchors.get(anchor_id)
            if callback is not None:
                callback()
            LOGGER.info('Message Browser Anchor clicked: %s', anchor_id)

    def set_opacity(self, opacity: int):
        opacity = min(255, max(0, opacity))
        self.overlay_grp.setStyleSheet(self.style.format(opacity, opacity))

    def restore_visibility(self):
        self.overlay_grp.setStyleSheet(self.style.format(self.bg_opacity, self.txt_opacity))

    def display(self, message: str='', duration: int=3000, immediate: bool=False, buttons: tuple=tuple()):
        if len(self.queue) > self.queue_limit:
            return

        self.queue.append(
            (self._force_word_wrap(message), duration, buttons,)
            )

        if not self.msg_timer.isActive() or immediate:
            self._next_entry(False)

    def display_confirm(self, message: str='', buttons: tuple=tuple(), immediate: bool=False):
        self.display(message, 1000, immediate, buttons)

    def display_exit(self):
        """ Immediately hide the current message """
        self.click_timer.start(100)
        self.msg_timer.stop()

        if self.btn_list:
            self.anchors = dict()
            for btn in self.btn_list:
                btn.deleteLater()
            self.btn_list = list()

        if self.queue:
            self._next_entry(False)
        else:
            self._init_fade_anim(False)
            QTimer.singleShot(300, self.hide_all)

    def _next_entry(self, called_from_timer: bool=True):
        """ Display the next entry in the queue """
        if self.btn_list:
            return

        if self.queue:
            message, duration, buttons = self.queue.pop(0)
            LOGGER.debug('Displaying: %s (%s)', message[:30], len(self.queue))
        else:
            self.display_exit()
            LOGGER.debug('Overlay stopping.')
            return

        if buttons:
            self.anchors = dict()
            self.btn_list = [self.create_button(btn) for btn in buttons]
            self.btn_box.show()
        else:
            self.btn_box.hide()

        if not self.use_msg_browser:
            self.text_label.setText(message)
            self.show_all()
            self.restore_visibility()
        else:
            message = f'<b>{self.parent.objectName()} {datetime.now().strftime("(%H:%M:%S)")}:</b><br />{message}'
            self.msg_browser.append(message)
            self.tab_widget_anim.blink()
            if self.msg_tab.currentIndex() != self.msg_tab_idx:
                self.msg_tab.setTabIcon(self.msg_tab_idx, IconRsc.get_icon('assignment_msg_new'))

        # Animate if not called from the queue timer
        if not called_from_timer and not self.message_active:
            self.overlay_grp.setUpdatesEnabled(False)
            self._init_fade_anim(True)
            QTimer.singleShot(150, self._enable_updates)

        QTimer.singleShot(1, self._adapt_size)
        self.message_active = True
        self.msg_timer.start(duration)

    def _enable_updates(self):
        self.overlay_grp.setUpdatesEnabled(True)

    def _init_fade_anim(self, fade_in: bool=True):
        if self.bg_anim.fade_anim.state() == QAbstractAnimation.Running:
            LOGGER.debug('Stopping running animation.')
            self.bg_anim.fade_anim.stop()

        if fade_in:
            self.bg_anim.fade((self.bg_color[0], self.bg_color[1], self.bg_color[2], 0), self.bg_color, 500)
        else:
            self.bg_anim.fade(self.bg_color, (self.bg_color[0], self.bg_color[1], self.bg_color[2], 0), 300)

    def create_button(self, button):
        """ Dynamic button creation on request """
        txt, callback = button

        if self.use_msg_browser and callback is not None:
            anchor_id = f'{KnechtUuidGenerator.create_id().toString()[1:-1]}'
            anchor = f'<a name="{anchor_id}" href="#{anchor_id}">{txt}</a>'
            self.msg_browser.append(anchor)
            self.anchors[anchor_id] = callback

        new_button = QtWidgets.QPushButton(txt, self.btn_box)
        new_button.setStyleSheet('background: rgba(80, 80, 80, 255); color: rgb(230, 230, 230);')
        self.btn_box.layout().addWidget(new_button, 0, Qt.AlignLeft)

        new_button.pressed.connect(callback or self.display_exit)

        return new_button

    def hide_all(self):
        if not self.msg_timer.isActive() and not self.queue:
            self.hide()
            self.btn_box.hide()
            self.message_active = False

    def show_all(self):
        self.show()

    @staticmethod
    def _force_word_wrap(message: str) -> str:
        """ Force white space in too long words """
        word_chr_limit = 35
        new_message = ''

        # Find words aswell as whitespace \W
        for word in re.findall("[\w']+|[\W]+", message):
            if not len(word) > word_chr_limit:
                new_message += word
                continue

            # Add a hard line break in words longer than the limit
            for start in range(0, len(word), word_chr_limit):
                end = start + word_chr_limit
                new_message += word[start:end] + '\n'

        # Return without trailing space
        return new_message


class MainWindowOverlay(InfoOverlay):
    y_offset_factor = 0.15
    x_offset_factor = 0.35
    bg_opacity = 180


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
