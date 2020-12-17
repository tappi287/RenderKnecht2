from pathlib import Path, WindowsPath
from datetime import datetime

from threading import Thread
import shutil

from PySide2.QtCore import QObject, Qt, QTimer, Signal
from PySide2.QtWidgets import QWidget, QHBoxLayout, QLabel, QLineEdit, QToolButton, QGroupBox, QPushButton, QTextBrowser

from modules.globals import Resource
from modules.gui.gui_utils import SetupWidget
from modules.gui.ui_resource import IconRsc
from modules.gui.widgets.path_util import SetDirectoryPath
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class ThreadSignals(QObject):
    update = Signal(str)


def copy_material_dirs(target_path: Path, sorted_src_dirs: dict, signal_obj: ThreadSignals):
    for target_dir in target_path.iterdir():
        if target_dir.name not in sorted_src_dirs:
            continue

        src_dir = sorted_src_dirs[target_dir.name]['path']

        # Delete Target directory
        shutil.rmtree(target_dir.as_posix(), ignore_errors=True)

        # Copy directory contents
        shutil.copytree(src_dir.as_posix(), target_dir.as_posix(), dirs_exist_ok=True)

        signal_obj.update.emit(f'Updated {target_dir.name} in {str(WindowsPath(target_dir))}')


class MaterialMerger(QWidget):
    def __init__(self, ui):
        """ Dialog to merge Materials directory of different models

        :param modules.gui.main_ui.KnechtWindow ui: Main Window
        """
        super(MaterialMerger, self).__init__(ui)
        SetupWidget.from_ui_file(self, Resource.ui_paths['knecht_material_merger'])
        self.setWindowTitle('AViT Material Merger')

        self.src_path_objects = list()

        self.titleLabel: QLabel
        self.titleLabel.setText('''
        <p>Vergleicht beliebige Quell -Materials- Verzeichnisse mit dem Ziel Material Verzeichnis. Ersetzt nur 
        Unterordner die bereits im Ziel Verzeichniss bestehen. Die Quell-Verzeichnisse werden gewählt 
        anhand der jüngsten enthaltenen CSB Datei. <b>Erstellt kein BackUp!</b></p>
        <table>
            <tr>
                <th>Ziel</th>
                <th>Aktion</th>
                <th>Quelle</th>
            </tr>
            <tr>
                <td>ABC001</td>
                <td> &lt; - - </td>
                <td>ABC001</td>
            </tr>
            <tr>
                <td></td>
                <td>x</td>
                <td>DEF001</td>
            </tr>
            <tr>
                <td>DBC000</td>
                <td> &lt; - - </td>
                <td>DBC000</td>
            </tr>
        </table>
        ''')
        self.titleLabel.setWordWrap(True)

        self.srcGrp: QGroupBox
        self.srcGrp.setTitle(_('Quell-Verzeichnisse'))
        self.targetGrp: QGroupBox
        self.targetGrp.setTitle(_('Ziel-Verzeichnis'))

        self.addSrcBtn: QPushButton
        self.addSrcBtn.setText(_('Quelleordner hinzufügen'))
        self.addSrcBtn.pressed.connect(self.add_source_path_object)

        self.mergeBtn: QPushButton
        self.mergeBtn.setText(_('Vereinen'))
        self.mergeBtn.pressed.connect(self.merge)

        self.target_path_widget = SetDirectoryPath(self, line_edit=self.targetPathLineEdit,
                                                   tool_button=self.targetPathToolBtn, reject_invalid_path_edits=True)

        self.resultBrowser.append('Displaying results.')

        self.copy_thread = None
        self.thread_timer = QTimer()
        self.thread_timer.setInterval(1000)
        self.thread_timer.setSingleShot(False)
        self.thread_timer.timeout.connect(self.update_copy_thread_status)

        # -- Create initial source path widget
        self.add_source_path_object()

        self.sorted_src_dirs = dict()

    def remove_source_path_object(self):
        btn = self.sender()
        src_path = [s for s in self.src_path_objects if s == btn.src_path][0]

        for i in range(src_path.layout.count()):
            w = src_path.layout.itemAt(i).widget()
            w.deleteLater()
        src_path.layout.deleteLater()
        src_path.path_widget.deleteLater()
        src_path.deleteLater()

    def add_source_path_object(self):
        src_path = QObject(self)
        h_layout = QHBoxLayout(self.srcGrp)
        label = QLabel(f'Source_{len(self.src_path_objects)}')
        h_layout.addWidget(label)
        line_edit = QLineEdit(self.srcGrp)
        h_layout.addWidget(line_edit)
        tool_btn = QToolButton(self.srcGrp)
        tool_btn.setText('...')
        h_layout.addWidget(tool_btn)
        del_btn = QPushButton(self.srcGrp)
        del_btn.setIcon(IconRsc.get_icon('delete'))
        h_layout.addWidget(del_btn)
        del_btn.src_path = src_path
        del_btn.released.connect(self.remove_source_path_object)
        path_widget = SetDirectoryPath(self, line_edit=line_edit, tool_button=tool_btn)

        src_path.layout = h_layout
        src_path.path_widget = path_widget

        # Save widget in path objects list and add widget to source path layout
        self.src_path_objects.append(src_path)
        self.srcLayout.addLayout(h_layout)

    def merge(self):
        self.mergeBtn.setEnabled(False)
        self.resultBrowser: QTextBrowser
        self.resultBrowser.clear()
        self.resultBrowser.append('<h4>' + _('Vereine Material Verzeichnisse') + '</h4>')

        if self.target_path_widget.path is None or not self.target_path_widget.path.exists():
            self.resultBrowser.append(
                f'<span style="color: red;">Could not locate Target path: {self.target_path_widget.path}</span>')
            return

        target_dir_names = [target_dir.name for target_dir in self.target_path_widget.path.iterdir()]

        # -- Collect source Materials
        src_dirs = dict()
        for src_path in self.src_path_objects:
            # -- Check src path exists
            p: Path = src_path.path_widget.path
            if p is None or p.is_file() or not p.exists():
                continue

            # -- Iterate sub Material directory
            for d in p.iterdir():
                # -- Skip source dirs not in target path
                if not d.name in target_dir_names:
                    continue

                # -- Get contained CSB files
                csb = [c for c in d.glob('*.csb')]
                if not csb:
                    continue
                csb = csb[0]
                path_entry = {'path': d, 'ctime': csb.stat().st_mtime}
                if d.name not in src_dirs:
                    src_dirs[d.name] = list()
                src_dirs[d.name].append(path_entry)

        # -- Sort entries by CSB File change time
        self.sorted_src_dirs = dict()
        for dir_name, entry_list in src_dirs.items():
            self.sorted_src_dirs[dir_name] = sorted(entry_list, key=lambda k: k['ctime'], reverse=True)[0]
            if len(entry_list) > 1:
                self.resultBrowser.append(dir_name)
                self.resultBrowser.append(
                    f'Found {dir_name} in multiple sources. Selecting newer file from: '
                    f'{self.sorted_src_dirs[dir_name]["path"].parent.parent.name} from '
                    f'{datetime.utcfromtimestamp(self.sorted_src_dirs[dir_name]["ctime"]).strftime("%d.%m.%Y %H:%M")}')

                for e in entry_list:
                    self.resultBrowser.append(
                        f'Checked: {e["path"].parent.parent.name} - CSB last modified date: '
                        f'{datetime.utcfromtimestamp(e["ctime"]).strftime("%d.%m.%Y %H:%M")}')

        del src_dirs

        # -- Replace Material directories in target dir
        thread_signals = ThreadSignals()
        thread_signals.update.connect(self.resultBrowser.append)
        self.copy_thread = Thread(target=copy_material_dirs,
                                  args=(self.target_path_widget.path, self.sorted_src_dirs, thread_signals))
        self.copy_thread.start()
        self.thread_timer.start()

    def update_copy_thread_status(self):
        if self.copy_thread is None:
            return

        if self.copy_thread.is_alive():
            return

        self.resultBrowser.append('Copy thread finished!')
        self.report_untouched_materials()
        self.thread_timer.stop()
        self.mergeBtn.setEnabled(True)

    def report_untouched_materials(self):
        """ Report Materials not copied into target
            Directories existing in the target path but not in any source path
        """
        for target_dir in self.target_path_widget.path.iterdir():
            if target_dir.name not in self.sorted_src_dirs:
                self.resultBrowser.append(f'{target_dir.name} was not in any source directory and was not updated.')
