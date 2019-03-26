import time
from pathlib import Path
from queue import Queue
from threading import Thread
from typing import List

from PySide2.QtCore import QObject, Signal, Slot

from modules.idgen import KnechtUuidGenerator
from modules.itemview.item import KnechtItem
from modules.knecht_objects import KnData, KnPr, KnTrim
from modules.knecht_utils import shorten_model_name
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class KnechtDataThreadSignals(QObject):
    finished = Signal(Path, KnechtItem)
    error = Signal(str)
    progress_msg = Signal(str)
    worker_progress = Signal(str)


class KnechtDataThread(Thread):
    def __init__(self, file: Path, xl_queue: Queue):
        super(KnechtDataThread, self).__init__()
        self.file = file
        self.data_queue = xl_queue
        self.daemon = True

        self.signals = KnechtDataThreadSignals()
        self.finished = self.signals.finished
        self.error = self.signals.error
        self.worker_progress = self.signals.worker_progress
        self.progress_msg = self.signals.progress_msg

    def run(self):
        LOGGER.debug('Excel data to KnechtModel thread started.')
        self.progress_msg.emit(_('Excel Daten werden konvertiert...'))
        time.sleep(0.01)
        kn_data = self.data_queue.get()

        kn_reader = KnechtDataToModel(kn_data)
        kn_reader.progress_signal = self.worker_progress
        self.worker_progress.connect(self._work_progress)
        root_item = kn_reader.create_root_item()

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


class KnechtDataToModel:
    progress_signal = None

    def __init__(self, data: KnData):
        self.data = data

        self.id_gen = KnechtUuidGenerator()
        self.root_item = KnechtItem()

    def _show_progress(self, msg: str):
        if self.progress_signal is None:
            return
        self.progress_signal.emit(msg)

    def create_root_item(self):
        self.create_items()
        LOGGER.debug('Created %s items from ExcelData.', self.root_item.childCount())
        return self.root_item

    def create_items(self):
        progress_idx = 0

        for trim in self.data.models:
            model = trim.model

            if model not in self.data.selected_models:
                continue

            progress_idx += 1
            self._show_progress(
                _('Erstelle Model {} {:02d}/{:02d}...').format(
                    model, progress_idx, len(self.data.selected_models)
                    )
                )

            # -- Create trimline --
            if self.data.read_trim:
                data = (f'{self.root_item.childCount():03d}', trim.model_text, model, 'trim_setup', '',
                        self.id_gen.create_id(), f'{trim.market} - {trim.gearbox}')

                trim_item = KnechtItem(self.root_item, data)
                self.create_pr_options(trim.iterate_trim_pr(), trim_item)
                self.root_item.append_item_child(trim_item)

            # -- Create options --
            if self.data.read_options:
                # Filter rows matching E
                data = (f'{self.root_item.childCount():03d}', f'{trim.model_text} Options', model, 'options', '',
                        self.id_gen.create_id(), f'{trim.market} - {trim.gearbox}')
                options_item = KnechtItem(self.root_item, data)
                self.create_pr_options(trim.iterate_optional_pr(), options_item)
                self.root_item.append_item_child(options_item)

            # -- Create packages --
            if self.data.read_packages:
                self.create_packages(trim)

            if self.data.read_fakom:
                self.create_fakom(trim)

    def create_packages(self, trim: KnTrim):
        for pkg in trim.iterate_packages():
            if not pkg.child_count():
                continue

            # Create package parent item
            data = (f'{self.root_item.childCount():03d}',
                    f'{pkg.name} {pkg.desc} {trim.model} {trim.market}', pkg.name, 'package', '',
                    self.id_gen.create_id()
                    )
            pkg_item = KnechtItem(self.root_item, data)
            keep_package = False

            for pr in pkg.iterate_pr():
                if pr.family in self.data.selected_pr_families:
                    # Apply PR Family Filter to Packages
                    # If it contains any chosen PR Family, keep the package
                    keep_package = True

                pr_item = KnechtItem(pkg_item,
                                     (f'{pkg_item.childCount():03d}', pr.name, 'on', pr.family, '', '', pr.desc))
                pkg_item.append_item_child(pr_item)

            if pkg_item.childCount():
                if self.data.pr_fam_filter_packages and keep_package:
                    # Only create packages that contain PR Families in the filter
                    self.root_item.append_item_child(pkg_item)
                elif not self.data.pr_fam_filter_packages:
                    # Create all packages and do not apply any filtering
                    self.root_item.append_item_child(pkg_item)

    def create_pr_options(self, pr_iterator: List[KnPr], parent_item: KnechtItem):
        for pr in pr_iterator:
            if pr.family not in self.data.selected_pr_families:
                continue

            pr_item = KnechtItem(parent_item,
                                 (f'{parent_item.childCount():03d}', pr.name, 'on', pr.family, '', '', pr.desc)
                                 )
            parent_item.append_item_child(pr_item)

    def create_fakom(self, trim: KnTrim):
        model_short_desc = shorten_model_name(trim.model_text)

        # Create lists of List[KnPr] for SIB/VOS/LUM families
        sib_pr_ls = [pr for pr in trim.iterate_available_pr() if pr.family.casefold() == 'sib']
        sib_pr_codes = [pr.name for pr in sib_pr_ls]
        lum_pr_ls = [pr for pr in trim.iterate_available_pr() if pr.family.casefold() == 'lum']
        vos_pr_ls = [pr for pr in trim.iterate_available_pr() if pr.family.casefold() == 'vos']

        for color, sib_set in self.data.fakom.iterate_colors():
            valid_sib_set = sib_set.intersection(sib_pr_codes)
            if not valid_sib_set:
                continue

            # --- Iterate SIB Codes ---
            for sib_pr in sib_pr_ls:
                if sib_pr.name not in valid_sib_set:
                    # Skip seat covers not matching
                    continue

                # --- Iterate VOS Codes ---
                for vos_pr in vos_pr_ls:

                    # --- Iterate LUM Codes ---
                    for lum_pr in lum_pr_ls:

                        # Determine if all options belong to standard equipment L
                        fakom_type = 'fakom_option'
                        if not {sib_pr.value, vos_pr.value, lum_pr.value}.difference('L'):
                            fakom_type = 'fakom_setup'

                        self.create_fakom_item(
                            trim.model, model_short_desc, color, sib_pr.name, vos_pr.name,
                            lum_pr.name, sib_pr.desc, vos_pr.desc, lum_pr.desc, fakom_type
                            )

    def create_fakom_item(self, model, model_desc, color, sib, vos, lum, sib_text, vos_text, lum_text, fakom_type):
        # Create package parent item
        data = (f'{self.root_item.childCount():03d}', f'{model_desc} {color}-{sib}-{vos}-{lum}',
                model, fakom_type, '', self.id_gen.create_id())

        # Create FaKom item
        fa_item = KnechtItem(self.root_item, data)
        # Create FaKom item content
        color_item = KnechtItem(fa_item, (f'{fa_item.childCount():03d}', color, 'on'))
        sib_item = KnechtItem(fa_item, (f'{fa_item.childCount():03d}', sib, 'on', 'SIB', '', '', sib_text))
        vos_item = KnechtItem(fa_item, (f'{fa_item.childCount():03d}', vos, 'on', 'VOS', '', '', vos_text))
        lum_item = KnechtItem(fa_item, (f'{fa_item.childCount():03d}', lum, 'on', 'LUM', '', '', lum_text))

        for i in (color_item, sib_item, vos_item, lum_item):
            fa_item.append_item_child(i)

        self.root_item.append_item_child(fa_item)
