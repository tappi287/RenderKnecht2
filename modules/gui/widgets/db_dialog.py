import datetime
from pathlib import Path

from PySide2.QtCore import QTimer, Qt, Signal, Slot
from PySide2.QtGui import QMouseEvent
from PySide2.QtWidgets import QDialog, QLabel, QPushButton, QLineEdit

from modules.globals import Resource
from modules.gui.gui_utils import SetupWidget
from modules.gui.ui_resource import IconRsc
from modules.gui.widgets.message_box import AskToContinue
from modules.idgen import KnechtUuidGenerator as Kid
from modules.itemview.item import KnechtItem, KnechtItemStyle
from modules.itemview.model import KnechtModel
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.itemview.model_update import UpdateModel
from modules.itemview.tree_view_checkable import KnechtTreeViewCheckable
from modules.itemview.tree_view_utils import setup_header_layout
from modules.knecht_datapool import DatapoolController
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class DatapoolDialog(QDialog):
    finished = Signal(KnechtModel, Path)
    check_column = Kg.NAME

    # Close connection after 10 minutes of user inactivity
    timeout = 600000

    def __init__(self, ui):
        """ Dialog to import Datapool items

        :param modules.gui.main_ui.KnechtWindow ui: Main Window
        """
        super(DatapoolDialog, self).__init__(ui)
        SetupWidget.from_ui_file(self, Resource.ui_paths['knecht_datapool'])
        self.setWindowTitle('Datapool Import')

        self._asked_for_close = False
        self._current_project_name = ''
        self.ui = ui

        # Avoid db/thread polling within timeout
        self.action_timeout = QTimer()
        self.action_timeout.setSingleShot(True)
        self.action_timeout.setInterval(300)

        # --- Translations n Style ---
        self.project_icon: QLabel
        self.project_icon.setPixmap(IconRsc.get_pixmap('storage'))
        self.project_title: QLabel
        self.project_title.setText(_('Datapool Projekte'))
        self.image_icon: QLabel
        self.image_icon.setPixmap(IconRsc.get_pixmap('img'))
        self.image_title: QLabel
        self.image_title.setText(_('Bildeinträge'))
        self.details_btn: QPushButton
        self.details_btn.setText(_('Detailspalten anzeigen'))
        self.details_btn.toggled.connect(self.toggle_view_columns)
        self.filter_box: QLineEdit
        self.filter_box.setPlaceholderText(_('Im Baum tippen um zu filtern...'))

        # -- Trigger filter update for all views ---
        self.update_filter_timer = QTimer()
        self.update_filter_timer.setInterval(5)
        self.update_filter_timer.setSingleShot(True)
        self.update_filter_timer.timeout.connect(self.update_filter_all_views)

        self.filter_box: QLineEdit
        self.filter_box.textChanged.connect(self.update_filter_timer.start)

        # --- Init Tree Views ---
        self.project_view = KnechtTreeViewCheckable(self, None, filter_widget=self.filter_box,
                                                    replace=self.project_view)
        self.image_view = KnechtTreeViewCheckable(self, None, filter_widget=self.filter_box,
                                                  replace=self.image_view)

        # --- Database Connector ---
        self.dp = DatapoolController(self)
        self.dp.add_projects.connect(self.update_project_view)
        self.dp.add_images.connect(self.update_image_view)
        self.dp.error.connect(self.error)

        # Connection timeout
        self.connection_timeout = QTimer()
        self.connection_timeout.setInterval(self.timeout)
        self.connection_timeout.setSingleShot(True)
        self.connection_timeout.timeout.connect(self.connection_timed_out)

        # Make sure to end thread on App close
        self.ui.is_about_to_quit.connect(self.close)

        # Intercept mouse press events from project view
        self.org_view_mouse_press_event = self.project_view.mousePressEvent
        self.project_view.mousePressEvent = self.view_mouse_press_event

        # Start thread
        QTimer.singleShot(100, self.start_datapool_connection)

    def view_mouse_press_event(self, event: QMouseEvent):
        if event.buttons() == Qt.LeftButton and not self.action_timeout.isActive():
            idx = self.project_view.indexAt(event.pos())
            name = idx.siblingAtColumn(Kg.NAME).data(Qt.DisplayRole)
            self._current_project_name = name
            _id = idx.siblingAtColumn(Kg.ID).data(Qt.DisplayRole)
            LOGGER.debug('Project %s Id %s selected', name, _id)
            self.action_timeout.start()

            if _id:
                self.request_project(_id)

        self.org_view_mouse_press_event(event)

    def update_filter_all_views(self):
        # Do not filter project view
        self.project_view.filter_timer.stop()

        # Update image view filter
        if not self.filter_box.text():
            self.image_view.clear_filter()
        else:
            self.image_view.filter_timer.start()

    def start_datapool_connection(self):
        self.show_progress(_('Verbinde mit Datenbank'))
        self.dp.start()
        self.connection_timeout.start()

    @Slot(dict)
    def update_project_view(self, projects: dict):
        """ (Name, ModelYear, 'JobNo) """
        if not projects:
            return

        root_item = KnechtItem(None, ('', _('Bezeichnung'), _('Modelljahr'), _('Job'), '', _('Id')))

        for num_idx, (_id, project_data) in enumerate(projects.items()):
            data = (f'{num_idx:03d}', *project_data, '', str(_id))
            p_item = KnechtItem(root_item, data)
            KnechtItemStyle.style_column(p_item, 'render_preset', column=Kg.NAME)
            root_item.append_item_child(p_item)

        update_model = UpdateModel(self.project_view)
        update_model.update(KnechtModel(root_item))

        self.toggle_view_columns(self.details_btn.isChecked())
        self.project_view.setHeaderHidden(False)

    def request_project(self, _id: str):
        self.image_view.clear_filter()
        self.image_view.progress_msg.msg(_('Daten werden angefordert'))
        self.image_view.progress_msg.show_progress()

        self.dp.request_project(_id)
        self.connection_timeout.start()

    @Slot(dict)
    def update_image_view(self, images: dict):
        if not images:
            return

        root_item = KnechtItem(None, ('', _('Name'), _('Priorität'), _('Erstellt'), '', _('wagenbauteil Id')))

        for num_idx, (img_id, image_data) in enumerate(images.items()):
            """ (name, priority, created, pr_string, opt_id, produced_image_id) """
            name, priority, created, pr_string, opt_id, produced_image_id = image_data
            img_item = KnechtItem(root_item, (f'{num_idx:03d}', name, priority, created, '', str(opt_id)))
            KnechtItemStyle.style_column(img_item, 'preset', Kg.NAME)
            root_item.append_item_child(img_item)

        update_model = UpdateModel(self.image_view)
        update_model.update(KnechtModel(root_item, checkable_columns=[self.check_column]))

        self.toggle_view_columns(self.details_btn.isChecked())
        self.image_view.setHeaderHidden(False)
        self.image_view.check_items([], Kg.NAME, check_all=True)

    def create_presets(self):
        root_item = KnechtItem()

        for (src_index, item) in self.image_view.editor.iterator.iterate_view():
            if item.data(self.check_column, Qt.CheckStateRole) == Qt.Unchecked:
                continue

            name = item.data(Kg.NAME)
            data = (f'{root_item.childCount():03d}', name, '', 'preset', '',
                    Kid.convert_id(f'{root_item.childCount()}'))
            root_item.insertChildren(root_item.childCount(), 1, data)

        date = datetime.datetime.now().strftime('%Y%m%d')
        project = self._current_project_name.replace(' ', '_')
        self.finished.emit(KnechtModel(root_item), Path(f'{date}_{project}.xml'))

    def toggle_view_columns(self, checked: bool):
        columns = {Kg.ORDER, Kg.NAME, Kg.VALUE, Kg.TYPE, Kg.REF, Kg.ID, Kg.DESC}

        if checked:
            show_columns = {Kg.NAME, Kg.VALUE, Kg.TYPE, Kg.ID}
        else:
            show_columns = {Kg.NAME}

        for col in columns:
            self.project_view.setColumnHidden(col, col not in show_columns)
            self.image_view.setColumnHidden(col, col not in show_columns)

        self._setup_view_headers()

    def _setup_view_headers(self):
        setup_header_layout(self.project_view)
        setup_header_layout(self.image_view)

    @Slot(str)
    def error(self, error_msg):
        self.project_view.progress_msg.hide_progress()
        self.image_view.progress_msg.hide_progress()

        self.ui.msg(error_msg, 9000)

    @Slot(str)
    def show_progress(self, msg: str):
        self.project_view.progress_msg.msg(msg)
        self.project_view.progress_msg.show_progress()

        self.image_view.progress_msg.msg(_('Projekt auswählen'))
        self.image_view.progress_msg.show_progress()
        self.image_view.progress_msg.progressBar.setValue(0)

    def connection_timed_out(self):
        self.show_progress(_('Zeitüberschreitung'))
        self.ui.msg(_('Zeitüberschreitung bei Datenbankverbindung. Die Verbindung wurde automatisch getrennt.'), 12000)
        self.dp.close()

    def reject(self):
        self.close()

    def accept(self):
        self.create_presets()

        self._asked_for_close = True
        self.close()

    def closeEvent(self, close_event):
        LOGGER.debug('Datapool close event called. %s', close_event.type())
        if self._ask_abort_close():
            close_event.ignore()
            return False

        LOGGER.info('Datapool window close event triggered. Aborting database connection')
        # End thread
        if not self._finalize_dialog():
            close_event.ignore()
            return False

        close_event.accept()
        return True

    def _ask_abort_close(self):
        if self._asked_for_close:
            return False

        msg_box = AskToContinue(self)

        if not msg_box.ask(
            title=_('Importvorgang'),
            txt=_('Soll der Vorgang wirklich abgebrochen werden?'),
            ok_btn_txt=_('Ja'),
            abort_btn_txt=_('Nein'),
                ):
            # Cancel close
            return True

        # Close confirmed
        return False

    def _finalize_dialog(self, self_destruct: bool=True) -> bool:
        LOGGER.debug('Datapool dialog is finishing tasks.')
        if not self.dp.close():
            return False

        if self_destruct:
            self.deleteLater()
        return True
