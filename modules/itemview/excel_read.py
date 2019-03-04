import time
from pathlib import Path
from threading import Thread
from queue import Queue
from typing import List, Tuple

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


class KnechtExcelDataThread(Thread):
    def __init__(self, file: Path, queue: Queue):
        super(KnechtExcelDataThread, self).__init__()
        self.file = file
        self.queue = queue

        self.signals = KnechtExcelDataThreadSignals()
        self.finished = self.signals.finished
        self.error = self.signals.error
        self.progress_msg = self.signals.progress_msg

    def run(self):
        LOGGER.debug('Excel data to KnechtModel thread started.')
        self.progress_msg.emit(_('Excel Daten werden konvertiert...'))
        time.sleep(0.5)
        data = self.queue.get()

        xl_reader = KnechtExcelDataToModel(
            *data
            )
        root_item = xl_reader.create_root_item()

        if not root_item.childCount():
            self.error.emit(_('Konnte keinen Baum aus Excel Daten erstellen.'))
            self.finish()
            return

        self.finished.emit(self.file, root_item)
        self.finish()

    def finish(self):
        self.progress_msg.emit('')
        self.signals.deleteLater()


class KnechtExcelDataToModel:

    def __init__(self, data: ExcelData, models: List[str], pr_families: List[str],
                 read_trim: bool=True, read_options: bool=True, read_pkg: bool=True):
        self.data, self.models, self.pr_families = data, models, pr_families
        self.read_trim, self.read_options, self.read_pkg = read_trim, read_options, read_pkg

        self.id_gen = KnechtUuidGenerator()
        self.root_item = KnechtItem()

    def create_root_item(self):
        self.create_items()
        LOGGER.debug('Created %s items from ExcelData.', self.root_item.childCount())
        return self.root_item

    def create_items(self):
        # -- Model Columns
        model_column = self.data.models.columns[self.data.map.Models.ColumnIdx.model]
        model_desc_column = self.data.models.columns[self.data.map.Models.ColumnIdx.model_text]
        market_column = self.data.models.columns[self.data.map.Models.ColumnIdx.market]
        gearbox_column = self.data.models.columns[self.data.map.Models.ColumnIdx.gearbox]

        for idx, model in enumerate(sorted(self.models)):
            # Filter rows not matching -, P, E
            trim = self.data.pr_options.loc[~self.data.pr_options[model].isin(['-', 'P', 'E'])]
            options = self.data.pr_options.loc[self.data.pr_options[model].isin(['E'])]

            # Model info
            model_rows = self.data.models.loc[self.data.models[model_column] == model]
            model_desc = model_rows[model_desc_column].unique()[0]
            market = model_rows[market_column].unique()[0]
            gearbox = model_rows[gearbox_column].unique()[0]

            if self.read_trim:
                # Create trimline
                data = (f'{idx:03d}', model_desc, model, 'trim_setup', '',
                        self.id_gen.create_id(), f'{market} - {gearbox}')
                trim_item = KnechtItem(self.root_item, data)
                self.create_pr_options(trim, trim_item)
                self.root_item.append_item_child(trim_item)

            if self.read_options:
                # Create options
                data = (f'{idx:03d}', f'{model_desc} Options', model, 'options', '',
                        self.id_gen.create_id(), f'{market} - {gearbox}')
                options_item = KnechtItem(self.root_item, data)
                self.create_pr_options(options, options_item)
                self.root_item.append_item_child(options_item)

    def create_pr_options(self, trim, parent_item: KnechtItem):
        # -- PR Columns
        family_col = self.data.pr_options.columns[self.data.map.Pr.ColumnIdx.family]
        pr_col = self.data.pr_options.columns[self.data.map.Pr.ColumnIdx.pr]
        pr_text_col = self.data.pr_options.columns[self.data.map.Pr.ColumnIdx.pr_text]

        for pr_idx, pr_fam in enumerate(sorted(self.pr_families)):
            trim_rows = trim.loc[trim[family_col] == pr_fam]
            if trim_rows.empty:
                # Skip PR Families that do not match
                continue

            # Create Pr items
            for pr, pr_text in zip(trim_rows[pr_col].unique(), trim_rows[pr_text_col].unique()):
                pr_item = KnechtItem(parent_item, (f'{pr_idx:03d}', pr, 'on', pr_fam, '', '', pr_text))
                parent_item.append_item_child(pr_item)
