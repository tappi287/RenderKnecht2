import re
from pathlib import Path
from typing import Optional
from multiprocessing import process, Queue

import requests
import socketio
from PySide2.QtCore import QModelIndex, Signal

from modules import KnechtSettings
from modules.globals import get_settings_dir
from modules.knecht_objects import KnechtVariantList
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class WolkeServer:
    empty_model_index = QModelIndex()

    def __init__(self, status_signal: Signal, connected_signal: Signal, disconnected_signal: Signal,
                 send_var_signal: Signal, transfer_signal: Signal):
        self.sio = socketio.Client(reconnection=False)
        self.id = str()
        self.host = ''
        self.port = ''

        self.status_signal = status_signal
        self.connected_signal = connected_signal
        self.disconnected_signal = disconnected_signal
        self.send_variants = send_var_signal
        self.transfer_variants = transfer_signal

        self._setup_socketio_events()

    def _setup_socketio_events(self):
        @self.sio.on('connect')
        def on_connect():
            LOGGER.info('Connected to SocketIO Server')
            self.connected_signal.emit()
            self.status_signal.emit(_('Verbunden zum SteckbuchseReinRaus Server'))

        @self.sio.on('client_id_created')
        def on_client_id_created(data):
            self.id = data.get('id')
            self.status_signal.emit(_('Verbunden als {}').format(self.id))

        @self.sio.on('disconnect')
        def on_disconnect():
            LOGGER.info('Disconnected')
            self.disconnected_signal.emit()
            self.status_signal.emit(_('Verbindung getrennt.'))

        @self.sio.on('send_pr_string')
        def on_send_pr_string(data):
            LOGGER.debug('Received PR-String send event with data: %s', data)
            self.send_pr_string(data)

        @self.sio.on('transfer_presets')
        def on_transfer_presets(data):
            LOGGER.debug('Received Transfer Presets event with data: %s', data)
            self.transfer_presets(data)

    def transfer_presets(self, data: dict):
        url = f"{self.host}:{self.port}{data.get('url')}"
        file_hash = data.get("hash")
        self.status_signal.emit(_('Erhielt Transfer Presets Ereignis mit Daten:') +
                                f'<br />{data.get("document_label")} '
                                f'Presets: {len(data.get("presets"))}<br />'
                                f'File Hash: {file_hash}<br />'
                                f'File Url: {url}')

        file = self._get_plmxml(file_hash, url)
        if not file:
            return

        presets = list()
        for preset_name in data.get('presets'):
            preset_data = data.get('presets').get(preset_name)
            preset_data['name'] = preset_name
            variants = self._get_knecht_variants(file, preset_data)
            presets.append(variants)

        if presets:
            self.transfer_variants.emit({'label': data.get('document_label'), 'presets': presets})

    def send_pr_string(self, data: dict):
        url = f"{self.host}:{self.port}{data.get('url')}"
        file_hash = data.get("hash")
        self.status_signal.emit(_('Erhielt Senden PR-String Ereignis mit Daten:') +
                                f'<br />{data.get("name")}<br />'
                                f'PR-String: {len(data.get("result").split("+"))}<br />'
                                f'File Hash: {file_hash}<br />'
                                f'File Url: {url}')

        file = self._get_plmxml(file_hash, url)
        if not file:
            return

        # -- Prepare Variants
        variants = self._get_knecht_variants(file, data)

        # -- Send Variants
        if variants.variants:
            self.status_signal.emit('Triggered send operation')
            self.send_variants.emit(variants)

    def _get_knecht_variants(self, file, preset_data: dict) -> KnechtVariantList:
        # -- Prepare Variants
        variants = KnechtVariantList()
        variants.plm_xml_path = file.as_posix()
        variants.preset_name = preset_data.get('name')
        for pr in preset_data.get('result').split('+'):
            if pr == '':
                continue
            variants.add(self.empty_model_index, pr, pr)

        return variants

    def _get_plmxml(self, file_hash, url) -> Optional[Path]:
        # -- Prepare/download PlmXml file
        if file_hash not in KnechtSettings.wolke.get('files'):
            if not self.download(url, file_hash):
                return

        file = Path(KnechtSettings.wolke.get('files', dict())[file_hash])
        if not file.is_file():
            self.status_signal.emit(_('PlmXml Datei Eintrag gefunden aber keine lokale Datei vorhanden!'))
            return

        return file

    def download(self, url, file_hash) -> bool:
        output_dir = Path(get_settings_dir()) / 'plmxml_temp'
        if not output_dir.exists():
            output_dir.mkdir()
        r = requests.get(url)

        if r.status_code == 200 and r.headers.get("Content-Disposition", False) and \
                r.headers.get('Content-Type', '').startswith('application/xml'):
            file_name = re.findall("filename=(.+)", r.headers.get('Content-Disposition', ''))[0]
        else:
            self.status_signal.emit(_('Konnte Datei nicht heruterladen von: {}').format(url))
            return False

        try:
            plmxml_file = output_dir / file_name

            with open(plmxml_file, 'wb') as f:
                f.write(r.content)

            if not plmxml_file.is_file():
                self.status_signal.emit(_("Konnte Download Datei nicht finden: {}").format(plmxml_file))
                return False

            KnechtSettings.wolke.get('files', dict())[file_hash] = plmxml_file.as_posix()
            self.status_signal.emit(f'Downloaded plmxml to {plmxml_file.as_posix()}')
        except Exception as e:
            LOGGER.error(e)
            self.status_signal.emit(_('Konnte Download Datei nicht speichern: {}').format(url))

        return True

    @staticmethod
    def _create_send_data(data: dict = None):
        send_data = {
            'app'  : 'RenderKnecht', 'user': KnechtSettings.wolke.get('user'),
            'token': KnechtSettings.wolke.get("token")}

        if data:
            send_data.update(data)
        return send_data

    def connect_wolke(self):
        if not self.sio.connected:
            self.host = KnechtSettings.wolke.get('host')
            self.port = KnechtSettings.wolke.get('port')
            host = f"{self.host}:{self.port}"
            self.status_signal.emit(_('Verbinde mit {} als {}').format(host, KnechtSettings.wolke.get("user")))

            try:
                self.sio.connect(host, headers=self._create_send_data())
            except Exception as e:
                LOGGER.error('Error connecting to socketio Server: %s', e)
                self.status_signal.emit(_('<b>Konnte nicht verbinden mit {}: {}</b>').format(host, e))
                self.status_signal.emit(
                    _('Navigieren Sie zu Ihrer KnechtWolke Benutzer Profil and transferieren sie die '
                      'Einstellungen hier. Prüfen Sie die korrekte Adresse eingegeben zu haben '
                      'und das jener Server verfügbar ist von Ihrem lokalen Bereichsnetz. '
                      'Tun Sie auch diese App zu Ihrer Feuerwalzenweißliste hinzu.'))

    def disconnect_wolke(self):
        if self.sio.connected:
            self.sio.emit('client_disconnected', self._create_send_data())
            self.sio.disconnect()
            self.disconnected_signal.emit()
            self.status_signal.emit(_('Verbindung getrennt.'))
