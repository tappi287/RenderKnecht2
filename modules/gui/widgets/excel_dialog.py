from pathlib import Path
from threading import Thread

from PySide2.QtCore import QByteArray, QEvent, QFile, QIODevice, QObject, QTimer, Qt, Signal, Slot
from PySide2.QtWidgets import QAction, QDialog, QMenu, QTreeView, QCheckBox, QGroupBox, QLineEdit, QWidget, QTabWidget, \
    QLabel

from modules.globals import Resource
from modules.gui.gui_utils import SetupWidget, replace_widget
from modules.gui.ui_resource import IconRsc
from modules.gui.widgets.message_box import AskToContinue, GenericMsgBox
from modules.itemview.item import KnechtItem
from modules.itemview.model import KnechtModel
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.itemview.model_update import UpdateModel
from modules.itemview.tree_view import KnechtTreeView
from modules.itemview.tree_view_utils import KnechtTreeViewShortcuts, setup_header_layout
from modules.knecht_excel import ExcelData, ExcelReader
from modules.language import get_translation
from modules.log import init_logging
from modules.settings import KnechtSettings, Settings

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class ExcelReaderThreadSignals(QObject):
    finished = Signal(ExcelData)
    error = Signal(list)
    progress_msg = Signal(str)


class ExcelReaderThread(Thread):
    def __init__(self, file: Path):
        super(ExcelReaderThread, self).__init__()
        self.file = file

        self.signals = ExcelReaderThreadSignals()
        self.finished = self.signals.finished
        self.error = self.signals.error
        self.progress_msg = self.signals.progress_msg

    def run(self):
        LOGGER.debug('Excel file reader thread started: %s', self.file.name)
        xl = ExcelReader()
        self.progress_msg.emit(_('Excel Datei wird gelesen...'))
        result = xl.read_file(self.file)

        if result:
            self.progress_msg.emit(_('Daten übertragen...'))
            LOGGER.debug('Excel read succeded.')
            self.finished.emit(xl.data)
        else:
            LOGGER.debug('Excel read failed: %s', xl.errors)
            self.error.emit(xl.errors)

        self.signals.deleteLater()


class ExcelImportDialog(QDialog):
    finished = Signal(QDialog)

    pr_root_item = KnechtItem(data=(
        '', _('PR-Familie'), _('Beschreibung'),))
    models_root_item = KnechtItem(data=(
        '', _('Model'), _('Markt'), _('Beschreibung'), '', '', _('Getriebe')))

    class PrColumn:
        code = 1
        name = 2

    class ModelColumn:
        code = 1
        market = 2
        name = 3
        gearbox = 6

    class PrDefaultFilter:
        """ Filter will be populated from resource data """
        interior = list()
        exterior = list()

    def __init__(self, ui, file: Path):
        """ Dialog to set Excel V Plus import options

        :param modules.gui.main_ui.KnechtWindow ui: Main Window
        :param Path file:
        """
        super(ExcelImportDialog, self).__init__(ui)
        SetupWidget.from_ui_file(self, Resource.ui_paths['knecht_excel_gui'])
        self.ui = ui
        self.setWindowTitle(
            _('V-Plus Browser Leseoptionen')
            )

        self.file = file

        # --- Filter Buttons ---
        for a in (self.btn_filter_all, self.btn_filter_ext, self.btn_filter_int):
            # Use released trigger so we do not trigger an update on settings load
            a.released.connect(self.update_pr_view)

        # --- Clear filter on tab change ---
        self.tabWidget_Excel.currentChanged.connect(self._clear_tree_filter)

        # --- Init Tree Views ---
        self.treeView_Models = self._init_tree_view(self.treeView_Models)
        self.treeView_PrFam = self._init_tree_view(self.treeView_PrFam)

        # --- Reader Thread ---
        self.excel_thread = ExcelReaderThread(file)
        self.excel_thread.finished.connect(self.read_finished)
        self.excel_thread.error.connect(self.read_failed)
        self.excel_thread.progress_msg.connect(self.show_progress)

        # --- Init Icons + Translations ---
        self.option_box: QGroupBox
        self.option_box.setTitle(_('Optionen'))
        self.option_box.setEnabled(False)
        self.check_read_trim: QCheckBox
        self.check_read_trim.setText(_('Trimlines erstellen'))
        self.check_read_trim.setIcon(IconRsc.get_icon('car'))
        self.check_read_options: QCheckBox
        self.check_read_options.setText(_('Optionen erstellen'))
        self.check_read_options.setIcon(IconRsc.get_icon('options'))
        self.check_read_packages: QCheckBox
        self.check_read_packages.setText(_('Pakete erstellen'))
        self.check_read_packages.setIcon(IconRsc.get_icon('pkg'))

        self.family_box: QGroupBox
        self.family_box.setTitle(_('PR-Familien Filter Vorlagen'))
        self.family_box.setEnabled(False)
        self.btn_filter_all: QCheckBox
        self.btn_filter_all.setText(_('Alle PR-Familien'))
        self.btn_filter_int: QCheckBox
        self.btn_filter_int.setText(_('Interieur I/VX-13'))
        self.btn_filter_ext: QCheckBox
        self.btn_filter_ext.setText(_('Exterieur I/VX-13'))
        self.check_pr_fam_filter_packages: QCheckBox
        self.check_pr_fam_filter_packages.setIcon(IconRsc.get_icon('pkg'))
        self.check_pr_fam_filter_packages.setText(_('PR-Familien Filter auf Pakete anwenden'))

        self.lineEdit_filter: QLineEdit
        self.lineEdit_filter.setPlaceholderText(_('Zum filtern tippen ...'))

        self.tabWidget_Excel: QTabWidget
        self.tabWidget_Excel.setTabText(0, _('Modellfilter'))
        self.tabWidget_Excel.setTabIcon(0, IconRsc.get_icon('car'))
        self.tabWidget_Excel.setTabText(1, _('PR-Familien-Filter'))
        self.tabWidget_Excel.setTabIcon(1, IconRsc.get_icon('options'))

        self.label: QLabel
        self.label.setText(_('PR Familien auswählen die ausgelesen werden sollen.'))
        self.label_Models: QLabel
        self.label_Models.setText(_('Modelle auswählen die ausgelesen werden sollen.'))

        # --- Attributes ---
        self.data = None
        self.selected_models = list()
        self.selected_pr_families = list()

        self._asked_for_close = False
        self._settings_loaded = False
        self._abort = False
        self._data_ready_count = 0

        self.buttonBox.setEnabled(False)

        QTimer.singleShot(100, self._start_load)

    def _load_default_pr_filter(self):
        if self.PrDefaultFilter.interior:
            # Filter already loaded
            return

        f = QFile(Resource.icon_paths.get('pr_data'))
        try:
            f.open(QIODevice.ReadOnly)
            data: QByteArray = f.readAll()
            data: bytes = data.data()
            Settings.load_from_bytes(self.PrDefaultFilter, data)
        except Exception as e:
            LOGGER.error(e)
        finally:
            f.close()

    def _start_load(self):
        self.excel_thread.start()
        self.show_progress(_('Excel Daten werden geladen...'))

    @Slot(str)
    def show_progress(self, msg: str):
        self.treeView_Models.progress_msg.msg(msg)
        self.treeView_Models.progress_msg.show_progress()

    @Slot(list)
    def read_failed(self, errors: list):
        if self._abort:
            return

        txt = [x+'\n' for x in errors]
        msg_box = GenericMsgBox(self, _('Excel Import Fehler'), ''.join(txt), icon_key='excel')
        msg_box.exec_()
        self._asked_for_close = True
        self.close()

    @Slot(ExcelData)
    def read_finished(self, data):
        if self._abort:
            return

        self.data = data
        models = self.models_root_item.copy()
        pr_fam = self.pr_root_item.copy()

        for idx, d in enumerate(self.data.get_models()):
            models.insertChildren(
                models.childCount(), 1, (f'{idx:01d}', d[0], d[1], d[2], '', '', d[3])
                )

        for idx, d in enumerate(self.data.get_pr_families()):
            pr_fam.insertChildren(
                pr_fam.childCount(), 1, (f'{idx:01d}', d[0], d[1])
                )

        # Update View Models
        update_models = UpdateModel(self.treeView_Models)
        update_models.finished.connect(self._data_ready)
        update_models.update(KnechtModel(models, checkable_columns=[self.ModelColumn.code]))

        update_pr = UpdateModel(self.treeView_PrFam)
        update_pr.finished.connect(self._data_ready)
        update_pr.update(KnechtModel(pr_fam, checkable_columns=[self.PrColumn.code]))

    def _data_ready(self):
        self._data_ready_count += 1
        if self._data_ready_count < 2:
            return

        self._setup_tree_columns()
        self.buttonBox.setEnabled(True)
        self.family_box.setEnabled(True)
        self.option_box.setEnabled(True)

        self._setup_header_width()
        self._load_default_pr_filter()
        self.load_settings()

    def update_pr_view(self):
        pr_all, pr_int, pr_ext = self.btn_filter_all.isChecked(), self.btn_filter_int.isChecked(), \
                                 self.btn_filter_ext.isChecked()
        pr_family_filter = list()

        LOGGER.debug('Updating PR-Family view, All:%s, Int:%s, Ext:%s', pr_all, pr_int, pr_ext)
        if pr_int:
            pr_family_filter += self.PrDefaultFilter.interior
        if pr_ext:
            pr_family_filter += self.PrDefaultFilter.exterior

        self.check_items(pr_family_filter, self.PrColumn.code, self.treeView_PrFam, check_all=pr_all)

    def check_items(self, check_items: list, column: int, view: KnechtTreeView,
                    check_all: bool=False, check_none: bool=False):
        for (src_index, item) in self._iter_view(view, column):
            value, item_value = item.data(column, role=Qt.DisplayRole), None

            if value in check_items or check_all and not check_none:
                item_value = Qt.Checked
            else:
                item_value = Qt.Unchecked

            view.model().sourceModel().setData(src_index, item_value, Qt.CheckStateRole)

    @staticmethod
    def _iter_view(view: KnechtTreeView, column: int):
        for (src_index, item) in view.editor.iterator.iterate_view(column=column):
            yield src_index, item

    def load_settings(self) -> bool:
        if self._settings_loaded:
            return True

        for entry in KnechtSettings.excel:
            if entry.get('file') == self.file.as_posix():
                LOGGER.debug('Loading import setting for %s', self.file.name)
                break
        else:
            self.update_pr_view()
            return False

        # Restore filter settings
        for box in [self.btn_filter_all, self.btn_filter_int, self.btn_filter_ext, self.check_pr_fam_filter_packages,
                    self.check_read_trim, self.check_read_options, self.check_read_packages]:
            check_state = entry.get(box.objectName())

            if check_state is not None:
                if check_state == 2:
                    check_state = Qt.Checked
                else:
                    check_state = Qt.Unchecked
                box.setCheckState(check_state)

        # Restore checked models
        self.check_items(
            entry.get('models') or list(), self.ModelColumn.code, self.treeView_Models
            )
        # Restore checked Pr Families
        self.check_items(
            entry.get('pr_families') or list(), self.PrColumn.code, self.treeView_PrFam
            )

        self._settings_loaded = True
        return True

    def save_settings(self):
        settings = dict(file=self.file.as_posix())
        settings['models'] = list()
        settings['pr_families'] = list()

        # Save filter setting
        for box in [self.btn_filter_all, self.btn_filter_int, self.btn_filter_ext, self.check_pr_fam_filter_packages,
                    self.check_read_trim, self.check_read_options, self.check_read_packages]:
            settings.update({box.objectName(): int(box.checkState())})
        # Save model selection
        for (src_index, item) in self._iter_view(self.treeView_Models, self.ModelColumn.code):
            if item.isChecked(self.ModelColumn.code):
                settings['models'].append(str(item.data(self.ModelColumn.code)))
        # Save PR Family selection
        for (src_index, item) in self._iter_view(self.treeView_PrFam, self.PrColumn.code):
            if item.isChecked(self.PrColumn.code):
                settings['pr_families'].append(str(item.data(self.PrColumn.code)))

        # Update attributes for outside access
        self.selected_models = settings.get('models')
        self.selected_pr_families = settings.get('pr_families')

        # Remove existing entry for this file
        for entry in KnechtSettings.excel:
            if entry.get('file') == self.file.as_posix():
                KnechtSettings.excel.remove(entry)

        # Prepend setting entry
        KnechtSettings.excel.insert(0, settings)

        # Only keep the last 5 number of items
        if len(KnechtSettings.excel) > 5:
            KnechtSettings.excel = KnechtSettings.excel[:5]

        KnechtSettings.add_recent_file(self.file.as_posix(), 'xlsx')

        LOGGER.debug('Saved: %s', KnechtSettings.excel[0])

    def _setup_header_width(self):
        setup_header_layout(self.treeView_Models)
        setup_header_layout(self.treeView_PrFam)
        self.treeView_Models.header().resizeSection(1, 120)
        self.treeView_PrFam.header().resizeSection(1, 110)

    def _setup_tree_columns(self):
        # Hide ID columns
        for c in (Kg.ORDER, Kg.REF, Kg.ID):
            self.treeView_Models.hideColumn(c)
            self.treeView_Models.setHeaderHidden(False)
        for c in (0, 3, 4, 5, 6):
            self.treeView_PrFam.hideColumn(c)
            self.treeView_PrFam.setHeaderHidden(False)

    def _clear_tree_filter(self):
        self.treeView_PrFam.clear_filter()
        self.treeView_Models.clear_filter()

    def _init_tree_view(self, tree_view: QTreeView) -> KnechtTreeView:
        """ Replace the UI Designer placeholder tree views """
        parent = tree_view.parent()
        new_view = KnechtTreeView(parent, None)
        replace_widget(tree_view, new_view)

        # Setup filter widget
        new_view.filter_text_widget = self.lineEdit_filter
        # Setup keyboard shortcuts
        new_view.shortcuts = KnechtTreeViewShortcuts(new_view)
        new_view.context = ExcelContextMenu(self, new_view)

        # Update with placeholder Model to avoid access to unset attributes
        UpdateModel(new_view).update(KnechtModel())
        new_view.setHeaderHidden(True)

        return new_view

    def _ask_close(self):
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

        return False

    def reject(self):
        self.close()

    def accept(self):
        self.save_settings()
        self._finish_dialog(False)
        self.finished.emit(self)
        self.done(0)

    def _finish_dialog(self, self_destruct: bool=True):
        self._abort = True
        if self.excel_thread.is_alive():
            self.excel_thread.join()

        if self_destruct:
            self.deleteLater()

    def closeEvent(self, close_event):
        if self._ask_close():
            close_event.ignore()
            return False

        LOGGER.info('V Plus Browser window close event triggered. Aborting excel conversion')
        # End thread
        close_event.accept()
        self._finish_dialog()


class ExcelContextMenu(QMenu):
    def __init__(self, dialog: ExcelImportDialog, view: KnechtTreeView):
        super(ExcelContextMenu, self).__init__('Tree_Context', dialog)
        self.dialog = dialog

        self.select_all = QAction(IconRsc.get_icon('check_box'), _('Alle Einträge auswählen'))
        self.select_all.triggered.connect(self.select_all_items)
        self.select_none = QAction(IconRsc.get_icon('check_box_empty'), _('Alle Einträge abwählen'))
        self.select_none.triggered.connect(self.select_no_items)
        self.addActions([self.select_none, self.select_all])

        self.view = view
        self.view.installEventFilter(self)

    def select_all_items(self):
        self.dialog.check_items(
            [], self.get_column(), self.view, check_all=True
            )

    def select_no_items(self):
        self.dialog.check_items(
            [], self.get_column(), self.view, check_none=True
            )

    def get_column(self) -> int:
        if self.view is self.dialog.treeView_Models:
            return self.dialog.ModelColumn.code
        else:
            return self.dialog.PrColumn.code

    def eventFilter(self, obj: QObject, event:QEvent):
        if obj not in [self.dialog.treeView_PrFam, self.dialog.treeView_Models]:
            return False

        if event.type() == QEvent.ContextMenu:
            self.view = obj
            self.popup(event.globalPos())
            return True

        return False
