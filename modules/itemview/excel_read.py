import time
from pathlib import Path
from queue import Queue
from threading import Thread

from PySide2.QtCore import QObject, Signal, Slot

from modules.idgen import KnechtUuidGenerator
from modules.itemview.item import KnechtItem
from modules.knecht_excel import ExcelData
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class KnechtExcelDataThreadSignals(QObject):
    finished = Signal(Path, KnechtItem)
    error = Signal(str)
    progress_msg = Signal(str)
    worker_progress = Signal(str)


class KnechtExcelDataThread(Thread):
    def __init__(self, file: Path, xl_queue: Queue):
        super(KnechtExcelDataThread, self).__init__()
        self.file = file
        self.xl_queue = xl_queue

        self.signals = KnechtExcelDataThreadSignals()
        self.finished = self.signals.finished
        self.error = self.signals.error
        self.worker_progress = self.signals.worker_progress
        self.progress_msg = self.signals.progress_msg

    def run(self):
        LOGGER.debug('Excel data to KnechtModel thread started.')
        self.progress_msg.emit(_('Excel Daten werden konvertiert...'))
        time.sleep(0.01)
        data = self.xl_queue.get()

        xl_reader = KnechtExcelDataToModel(data)
        xl_reader.progress_signal = self.worker_progress
        self.worker_progress.connect(self._work_progress)
        root_item = xl_reader.create_root_item()

        if not root_item.childCount():
            self.error.emit(_('Konnte keinen Baum aus Excel Daten erstellen.'))
            self.finish()
            return

        self.finished.emit(self.file, root_item)
        self.finish()

    @Slot(str)
    def _work_progress(self, msg: str):
        self.progress_msg.emit(msg)
        time.sleep(0.02)

    def finish(self):
        self.progress_msg.emit('')
        self.signals.deleteLater()


class KnechtExcelDataToModel:
    pr_family_cache = dict(PR_Code='PR_Family_Code')
    progress_signal = None

    def __init__(self, data: ExcelData):
        self.data = data

        self.id_gen = KnechtUuidGenerator()
        self.root_item = KnechtItem()

    def _show_progress(self, msg: str):
        if self.progress_signal is None:
            return
        self.progress_signal.emit(msg)

    def create_root_item(self):
        self.update_pr_family_cache()
        self.create_items()
        LOGGER.debug('Created %s items from ExcelData.', self.root_item.childCount())
        return self.root_item

    def update_pr_family_cache(self):
        if self.data.pr_options.empty:
            return

        pr_col = self.data.pr_options.columns[self.data.map.Pr.ColumnIdx.pr]
        family_col = self.data.pr_options.columns[self.data.map.Pr.ColumnIdx.family]

        pr_codes = self.data.pr_options[pr_col].unique()
        self._show_progress(_('Indiziere {} PR Codes').format(len(pr_codes)))

        for pr in pr_codes:
            pr_rows = self.data.pr_options.loc[self.data.pr_options[pr_col] == pr]
            pr_fam = pr_rows[family_col].unique()[0]
            self.pr_family_cache[pr] = pr_fam

        LOGGER.debug('Indexed %s PR-Codes to PR Families.', len(self.pr_family_cache))

    def create_items(self):
        # -- Model Columns
        model_column = self.data.models.columns[self.data.map.Models.ColumnIdx.model]
        model_desc_column = self.data.models.columns[self.data.map.Models.ColumnIdx.model_text]
        market_column = self.data.models.columns[self.data.map.Models.ColumnIdx.market]
        gearbox_column = self.data.models.columns[self.data.map.Models.ColumnIdx.gearbox]

        for idx, model in enumerate(sorted(self.data.selected_models)):
            self._show_progress(_('Erstelle Model {} {:02d}/{:02d}...').format(
                model, idx, len(self.data.selected_models)))

            # Model info
            model_rows = self.data.models.loc[self.data.models[model_column] == model]
            model_desc = model_rows[model_desc_column].unique()[0]
            market = model_rows[market_column].unique()[0]
            gearbox = model_rows[gearbox_column].unique()[0]

            # -- Create trimline --
            if self.data.read_trim:
                # Filter rows ~not matching -, P, E
                trim = self.data.pr_options.loc[~self.data.pr_options[model].isin(['-', 'P', 'E'])]

                data = (f'{self.root_item.childCount():03d}', model_desc, model, 'trim_setup', '',
                        self.id_gen.create_id(), f'{market} - {gearbox}')
                trim_item = KnechtItem(self.root_item, data)
                self.create_pr_options(trim, trim_item)
                self.root_item.append_item_child(trim_item)

            # -- Create options --
            if self.data.read_options:
                # Filter rows matching E
                options = self.data.pr_options.loc[self.data.pr_options[model].isin(['E'])]

                data = (f'{self.root_item.childCount():03d}', f'{model_desc} Options', model, 'options', '',
                        self.id_gen.create_id(), f'{market} - {gearbox}')
                options_item = KnechtItem(self.root_item, data)
                self.create_pr_options(options, options_item)
                self.root_item.append_item_child(options_item)

            # -- Create packages --
            if self.data.read_packages:
                self.create_packages(model, market)

    def create_packages(self, model, market):
        if self.data.packages.empty:
            return

        # Package columns
        pkg_col = self.data.packages.columns[self.data.map.Packages.ColumnIdx.package]
        pkg_text_col = self.data.packages.columns[self.data.map.Packages.ColumnIdx.package_text]
        # PR columns inside package sheet
        pr_col = self.data.packages.columns[self.data.map.Packages.ColumnIdx.pr]
        pr_text_col = self.data.packages.columns[self.data.map.Packages.ColumnIdx.pr_text]

        # Extract rows not matching '-'
        pkg_rows = self.data.packages.loc[~self.data.packages[model].isin(['-'])]

        for pkg, pkg_text in zip(pkg_rows[pkg_col].unique(), pkg_rows[pkg_text_col].unique()):
            # Extract package content
            pkg_content = pkg_rows.loc[pkg_rows[pkg_col] == pkg]

            if pkg_content.empty:
                # Skip empty packages
                continue

            # Create package parent item
            data = (f'{self.root_item.childCount():03d}', f'{pkg} {pkg_text} {model} {market}',
                    pkg, 'package', '', self.id_gen.create_id())
            pkg_item = KnechtItem(self.root_item, data)
            keep_package = False

            for pr, pr_text in zip(pkg_content[pr_col], pkg_content[pr_text_col]):
                pr_fam = self.pr_family_cache.get(pr) or ''

                if pr_fam in self.data.selected_pr_families:
                    # Apply PR Family Filter to Packages
                    # If it contains any chosen PR Family, keep the package
                    keep_package = True

                pr_item = KnechtItem(pkg_item, (f'{pkg_item.childCount():03d}', pr, 'on', pr_fam, '', '', pr_text))
                pkg_item.append_item_child(pr_item)

            if pkg_item.childCount():
                if self.data.pr_fam_filter_packages and keep_package:
                    # Only create packages that contain PR Families in the filter
                    self.root_item.append_item_child(pkg_item)
                elif not self.data.pr_fam_filter_packages:
                    # Create all packages and do not apply any filtering
                    self.root_item.append_item_child(pkg_item)

    def create_pr_options(self, trim, parent_item: KnechtItem):
        # -- PR Columns
        family_col = self.data.pr_options.columns[self.data.map.Pr.ColumnIdx.family]
        pr_col = self.data.pr_options.columns[self.data.map.Pr.ColumnIdx.pr]
        pr_text_col = self.data.pr_options.columns[self.data.map.Pr.ColumnIdx.pr_text]

        for pr_idx, pr_fam in enumerate(sorted(self.data.selected_pr_families)):
            trim_rows = trim.loc[trim[family_col] == pr_fam]
            if trim_rows.empty:
                # Skip PR Families that do not match
                continue

            # Create Pr items
            for idx, (pr, pr_text) in enumerate(zip(trim_rows[pr_col].unique(), trim_rows[pr_text_col].unique())):
                pr_item = KnechtItem(parent_item, (f'{parent_item.childCount():03d}',
                                                   pr, 'on', pr_fam, '', '', pr_text))
                parent_item.append_item_child(pr_item)
