import os
from pathlib import Path, WindowsPath
from datetime import datetime

from threading import Thread
import shutil
from typing import List, Generator, Union

from PySide2.QtCore import QObject, Qt, QTimer, Signal, QUrl
from PySide2.QtGui import QDesktopServices
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

        signal_obj.update.emit(f'Updated <b>{target_dir.name}</b> from {str(WindowsPath(src_dir))}')


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

        self.resultBrowser: QTextBrowser
        self.resultBrowser.append('Displaying results.')

        self.copy_thread = None
        self.thread_timer = QTimer()
        self.thread_timer.setInterval(1000)
        self.thread_timer.setSingleShot(False)
        self.thread_timer.timeout.connect(self.update_copy_thread_status)

        # -- Create initial source path widget
        self.add_source_path_object()

        self.sorted_src_dirs = dict()

        self.tex_difference_dirs = dict()

    def remove_source_path_object(self):
        btn = self.sender()
        src_path = [s for s in self.src_path_objects if s == btn.src_path][0]

        for i in range(src_path.layout.count()):
            w = src_path.layout.itemAt(i).widget()
            w.deleteLater()

        self.src_path_objects.remove(src_path)

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
        self.resultBrowser.clear()
        self.resultBrowser.append('<h1>' + _('Vereine Material Verzeichnisse') + '</h1><br>')
        self.resultBrowser.append(f'Target: <i>{self.target_path_widget.path.as_posix()}</i>')

        if self.target_path_widget.path is None or not self.target_path_widget.path.exists():
            self.resultBrowser.append(
                f'<span style="color: red;">Could not locate Target path: {self.target_path_widget.path}</span>')
            return

        target_dir_names = [target_dir.name for target_dir in self.target_path_widget.path.iterdir()]

        # -- Collect source Materials
        src_material_csbs = dict()
        for idx, src in enumerate(self.src_path_objects):
            self.resultBrowser.append(f'Source #{idx}: <i>{src.path_widget.path.as_posix()}</i>')
            _src_csbs = self._collect_csb_materials(src.path_widget.path.iterdir(), target_dir_names)

            for src_dir_name, entry_ls in _src_csbs.items():
                if src_dir_name not in src_material_csbs:
                    src_material_csbs[src_dir_name] = list()
                for entry in entry_ls:
                    src_material_csbs[src_dir_name].append(entry)
                del src_dir_name, entry_ls
        self.resultBrowser.append('<br><br>')

        # -- Sort entries by CSB File change time
        self.sorted_src_dirs = dict()
        for dir_name, entry_list in src_material_csbs.items():

            self.sorted_src_dirs[dir_name] = sorted(entry_list, key=lambda k: k['ctime'], reverse=True)[0]
            if len(entry_list) > 1:
                self.resultBrowser.append(
                    f'Found <b>{dir_name}</b> in multiple sources. Selecting newer file from: '
                    f'{self.sorted_src_dirs[dir_name]["path"].parent.parent.name} from '
                    f'{datetime.utcfromtimestamp(self.sorted_src_dirs[dir_name]["ctime"]).strftime("%d.%m.%Y %H:%M")}')

                for e in entry_list:
                    self.resultBrowser.append(
                        f'Checked: {e["path"].parent.parent.name} - CSB last modified date: '
                        f'{datetime.utcfromtimestamp(e["ctime"]).strftime("%d.%m.%Y %H:%M")}')
                self.resultBrowser.append('<br>')

        del src_material_csbs

        # -- Filter out Materials that have differing textures
        for target_dir in self.target_path_widget.path.iterdir():
            if target_dir.name not in self.sorted_src_dirs:
                continue

            # -- Collect source and target texture file paths
            src_tex = self._collect_texture_files(self.sorted_src_dirs[target_dir.name]['path'])
            tgt_tex = self._collect_texture_files(target_dir)

            # -- Compare and exclude differing files
            if tgt_tex.symmetric_difference(src_tex):
                # -- Remove Entries that have differing textures
                self.sorted_src_dirs.pop(target_dir.name)
                # -- Add Report Entry
                self.tex_difference_dirs[target_dir.name] = tgt_tex.symmetric_difference(src_tex)

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

        self.resultBrowser.append('Copy thread finished!<br>')
        self.report_untouched_materials()
        self.export_html_report()
        self.thread_timer.stop()
        self.mergeBtn.setEnabled(True)

    def report_untouched_materials(self):
        """ Report Materials not copied into target
            Directories existing in the target path but not in any source path
        """
        self.resultBrowser.append('<h1>Material Merger Results</h1><br>')
        count = 0
        for target_dir in self.target_path_widget.path.iterdir():
            if target_dir.name in self.sorted_src_dirs or target_dir.name in self.tex_difference_dirs:
                continue
            self.resultBrowser.append(f'<b>{target_dir.name}</b> - '
                                      f'was not in any source directory and was not updated.<br>')
            count += 1

        if not count:
            self.resultBrowser.append('Source and target directories perfectly matched!? Did you cheat?<br>')

        self.resultBrowser.append('<h2>Materials with differing texture files</h2> <br>')
        if not self.tex_difference_dirs:
            self.resultBrowser.append('<i>Found no Materials with differing texture files.</i>')

        for target_dir in self.target_path_widget.path.iterdir():
            if target_dir.name not in self.tex_difference_dirs:
                continue

            filenames = ''.join([f'{f}; ' for f in self.tex_difference_dirs[target_dir.name]])
            self.resultBrowser.append(f'<b>{target_dir.name}</b> - '
                                      f'contained differing texture files: <i>{filenames}</i><br>')

    def export_html_report(self):
        # Report file path
        name = f'MaterialMerger_Report_{datetime.now().strftime("%d%m%Y_%H%M")}.html'
        report_file = QUrl.fromLocalFile(os.path.abspath(os.path.expanduser(f'~\\Documents\\{name}')))

        # Result browser html content
        html_data = str(self.resultBrowser.toHtml())

        # Write report
        try:
            with open(report_file.toLocalFile(), 'w') as f:
                f.write(html_data)
        except Exception as e:
            LOGGER.error(e)

        QDesktopServices.openUrl(report_file)

    @staticmethod
    def _collect_texture_files(directory: Path):
        return {file.name for file in directory.iterdir()
                if file.suffix.casefold() not in ('.csb', '.bak', '.texturepath', '.db') and not file.is_dir()}

    @staticmethod
    def _collect_csb_materials(directories: Union[List[Path]], target_dir_names: List[str]
                               ) -> dict:
        dir_data = dict()

        for src_dir in directories:
            # -- Skip directories not in target and non existing
            if src_dir is None or src_dir.is_file() or not src_dir.exists() or src_dir.name not in target_dir_names:
                continue

            # -- Get contained CSB files
            for d in src_dir.glob('*.csb'):
                # -- Add entry with directory path and CSB last modified time
                path_entry = {'path': src_dir, 'ctime': d.stat().st_mtime}

                if src_dir.name not in dir_data:
                    dir_data[src_dir.name] = list()

                dir_data[src_dir.name].append(path_entry)

        return dir_data
