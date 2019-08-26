from pathlib import Path

from PySide2.QtCore import QEvent, QUrl, Qt
from PySide2.QtWebEngineWidgets import QWebEngineView

from modules.globals import DOCS_HTML_FILEPATH, get_current_modules_dir
from modules.gui.widgets.path_util import path_exists
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class KnechtHelpPage(QWebEngineView):
    zoom = 1.5
    min_zoom = 1.0
    max_zoom = 3.0

    def __init__(self, ui):
        super(KnechtHelpPage, self).__init__(ui)
        self.ui = ui
        self.setWindowTitle(_('Dokumentation'))

        self.installEventFilter(self)
        self.setZoomFactor(KnechtHelpPage.zoom)
        self.load_docs()

    def load_docs(self):
        doc_file = Path(get_current_modules_dir()) / DOCS_HTML_FILEPATH

        if path_exists(doc_file):
            q = QUrl.fromLocalFile(doc_file.as_posix())
            LOGGER.info('Loading Documentation file: %s', q.toDisplayString())

            self.load(q)

    def update_zoom(self, amount):
        KnechtHelpPage.zoom = max(self.min_zoom, min(self.max_zoom, KnechtHelpPage.zoom + amount))
        self.setZoomFactor(KnechtHelpPage.zoom)
        self.ui.msg(f'Zoom {int(self.zoom * 100)}%', 500)

    def eventFilter(self, obj, event):
        if obj is None or event is None:
            return False

        if event.type() == QEvent.Type.Wheel and event.modifiers() == Qt.ControlModifier:
            if event.angleDelta().y() > 0:
                self.update_zoom(0.125)
            else:
                self.update_zoom(-0.125)

            event.accept()
            return True

        return False
