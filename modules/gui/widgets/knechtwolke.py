import os
import time
from datetime import datetime
from pathlib import Path
from typing import List
import concurrent.futures

from PySide2.QtCore import QObject, QTimer, Signal
from PySide2.QtWidgets import QTextBrowser

from modules import KnechtSettings
from modules.itemview.model_globals import KnechtModelGlobals as Kg
from modules.idgen import KnechtUuidGenerator as Kid
from modules.itemview.editor_create import ItemTemplates
from modules.itemview.item import KnechtItem
from modules.itemview.model import KnechtModel
from modules.knecht_objects import KnechtVariantList
from modules.knecht_utils import create_file_safe_name
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class KnechtWolkeUi(QObject):
    debounce = QTimer()
    debounce.setSingleShot(True)
    debounce.setInterval(3500)

    model_loaded = Signal(KnechtModel, Path)

    def __init__(self, ui):
        """

        :param modules.gui.main_ui.KnechtWindow ui:
        """
        super(KnechtWolkeUi, self).__init__(ui)
        self.ui = ui
        self.ui.connectLabel.setText(_('Verbindung herstellen'))

        # --- Prepare Host/Port/User edit ---
        self.ui.hostEdit.setText(KnechtSettings.wolke.get('host'))
        self.ui.portEdit.setText(KnechtSettings.wolke.get('port'))
        self.ui.userEdit.setText(KnechtSettings.wolke.get('user'))
        self.ui.tokenEdit.setText(KnechtSettings.wolke.get('token'))

        self.ui.hostEdit.textChanged.connect(self.update_host)
        self.ui.portEdit.textChanged.connect(self.update_port)
        self.ui.userEdit.textChanged.connect(self.update_user)
        self.ui.tokenEdit.textChanged.connect(self.update_token)

        # -- Connect Button --
        self.ui.connectBtn.setText(_('Verbinden'))
        self.ui.connectBtn.pressed.connect(self.wolke_connect)
        self.ui.disconnectBtn.setText(_('Trennen'))
        self.ui.disconnectBtn.pressed.connect(self.wolke_disconnect)
        self.ui.disconnectBtn.setEnabled(False)

        # -- Autostart --
        self.ui.autostartCheckBox.setText(_('Beim Anwendungsstart automatisch verbinden'))
        self.ui.autostartCheckBox.setChecked(KnechtSettings.wolke.get('autostart', False))
        self.ui.autostartCheckBox.toggled.connect(self.toggle_autostart)

        self.ui_elements = (self.ui.hostEdit, self.ui.portEdit, self.ui.userEdit, self.ui.connectBtn)

        self.model_loaded.connect(self.ui.main_menu.file_menu.model_loaded)

        # -- Setup Text Browser --
        self.txt: QTextBrowser = self.ui.textBrowser
        QTimer.singleShot(1000, self.delayed_setup)

        # -- Warning --
        self.txt.append(_('<b>ACHTUNG</b> Dieses Feature ist noch nicht für den produktiv Einsatz freigegeben. '
                          'Sockenströme verursachen weltumspannende Interpretierer Sperren! '
                          'Die Anwendung kann bei Verwendung jederzeit unvorhergesehen hängen. Vor dem testen '
                          'wichtige Dokumente sichern!'))

    def delayed_setup(self):
        self.ui.app.send_dg.socketio_status.connect(self.update_txt)
        self.ui.app.send_dg.socketio_connected.connect(self.connected)
        self.ui.app.send_dg.socketio_disconnected.connect(self.disconnected)
        self.ui.app.send_dg.socketio_send_variants.connect(self._send_variants)
        self.ui.app.send_dg.socketio_send_variants.connect(self._send_variants)
        self.ui.app.send_dg.socketio_transfer_variants.connect(self._transfer_variants)

        if KnechtSettings.wolke.get('autostart', False):
            self.wolke_connect()

    def connected(self):
        for ui_element in self.ui_elements:
            ui_element.setEnabled(False)
        self.ui.connectBtn.setText(_('Verbunden'))
        self.ui.disconnectBtn.setEnabled(True)

    def disconnected(self):
        for ui_element in self.ui_elements:
            ui_element.setEnabled(True)
        self.ui.connectBtn.setText(_('Verbinden'))
        self.ui.disconnectBtn.setEnabled(False)

    def _check_debounce(self) -> bool:
        if not self.debounce.isActive():
            self.debounce.start()
            return True
        return False

    def _send_variants(self, variant_ls: KnechtVariantList):
        self.ui.app.send_dg.send_variants(variant_ls)

    def _transfer_variants(self, data: dict):
        LOGGER.debug(f"Starting Wolke transfer for {len(data.get('presets', list()))} presets.")
        if not data.get('presets'):
            LOGGER.debug('Transfered Preset Data did not contain entries!')
            return

        try:
            self._create_document_from_transfer(data)
        except Exception as e:
            LOGGER.error('Error creating Knecht Document View from transferred Presets: %s', e)

    def _create_document_from_transfer(self, data):
        self.ui.main_menu.file_menu.load_save_mgr.load_start_time = time.time()
        new_file = Path(create_file_safe_name(f"{data.get('label', '')}_Transfer.xml"))
        preset_ls: List[KnechtVariantList] = data.get('presets', list())

        # -- Create Item Model
        root_item = KnechtItem()
        plmxml_path = preset_ls[0].plm_xml_path

        plmxml_item = self._create_top_level_item(root_item, ItemTemplates.plmxml)
        plmxml_item.setData(Kg.VALUE, plmxml_path)

        root_item.append_item_child(plmxml_item)
        sep = self._create_top_level_item(root_item, ItemTemplates.separator)
        root_item.append_item_child(sep)

        preset_item_ls = list()
        for idx, variant_ls in enumerate(preset_ls, start=1):
            variants = variant_ls.variants
            name = variant_ls.preset_name

            model = ''
            if len(variants) > 1:
                model = variants[1].value

            preset_item = self._create_top_level_item(root_item, ItemTemplates.preset)
            preset_item.setData(Kg.NAME, name)
            preset_item.setData(Kg.VALUE, model)
            preset_item.setData(Kg.ID, Kid.create_id())
            plmxml_ref = plmxml_item.copy(new_parent=preset_item)
            plmxml_ref.convert_to_reference()
            preset_item.append_item_child(plmxml_ref)

            for variant in variants:
                pr_item = KnechtItem(preset_item,
                                     (f'{preset_item.childCount():03d}', variant.value, 'on'))
                preset_item.append_item_child(pr_item)

            preset_item_ls.append(preset_item)
            root_item.append_item_child(preset_item)

        # -- Create some sugar template
        sep = self._create_top_level_item(root_item, ItemTemplates.separator)
        root_item.append_item_child(sep)

        #  - Viewsets -
        views = list()
        for shot in ('Shot_05', 'Shot_06'):
            view = self._create_top_level_item(root_item, ItemTemplates.viewset)
            view.setData(Kg.NAME, f'Viewset_{shot}')
            view.child(0).setData(Kg.VALUE, shot)
            root_item.append_item_child(view)
            views.append(view)

        #  - Output -
        out = self._create_top_level_item(root_item, ItemTemplates.output)
        out.setData(Kg.VALUE, os.path.expanduser('~'))
        root_item.append_item_child(out)

        #  - RenderPreset -
        sep = self._create_top_level_item(root_item, ItemTemplates.separator)
        root_item.append_item_child(sep)
        ren = self._create_top_level_item(root_item, ItemTemplates.render)
        ren.setData(Kg.NAME, f"Render_{data.get('label')}")
        out_ref = out.copy(new_parent=ren)
        out_ref.convert_to_reference()
        out_ref.setData(Kg.ORDER, f'{ren.childCount():03d}')
        ren.append_item_child(out_ref)

        for item in views + preset_item_ls:
            ref_item = item.copy()
            ref_item.removeChildren(0, ref_item.childCount())
            ref_item.convert_to_reference()
            ref_item.setData(Kg.ORDER, f'{ren.childCount():03d}')
            ren.append_item_child(ref_item)

        root_item.append_item_child(ren)
        sep = self._create_top_level_item(root_item, ItemTemplates.separator)
        root_item.append_item_child(sep)

        self.model_loaded.emit(KnechtModel(root_item), new_file)

    @staticmethod
    def _create_top_level_item(root_item: KnechtItem, template: KnechtItem) -> KnechtItem:
        item = template
        item = item.copy()
        item.setData(Kg.ORDER, f'{root_item.childCount():03d}')
        item.setData(Kg.ID, Kid.create_id())
        return item

    @staticmethod
    def toggle_autostart(v: bool):
        KnechtSettings.wolke['autostart'] = v

    @staticmethod
    def update_host(host):
        KnechtSettings.wolke['host'] = host

    @staticmethod
    def update_port(port):
        KnechtSettings.wolke['port'] = port

    @staticmethod
    def update_user(user):
        KnechtSettings.wolke['user'] = user

    @staticmethod
    def update_token(token):
        KnechtSettings.wolke['token'] = token

    def wolke_connect(self):
        if self._check_debounce():
            self.ui.app.send_dg.start_socketio.emit()

    def wolke_disconnect(self):
        if self._check_debounce():
            self.ui.app.send_dg.stop_socketio.emit()

    def update_txt(self, message):
        current_time = datetime.now().strftime('(%H:%M:%S)')
        self.txt.append(f'{current_time} {message}')
