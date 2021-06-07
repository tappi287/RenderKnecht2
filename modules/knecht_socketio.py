import re
from multiprocessing import Queue
from pathlib import Path
from queue import Empty
from threading import Event, Thread
from typing import Optional, Union

import requests
from PySide2.QtCore import QModelIndex, Signal
from knecht_socketio_client import SocketProcess
from knecht_socketio_client.singleton import SingleInstanceException

from modules import KnechtSettings
from modules.globals import get_settings_dir
from modules.knecht_objects import KnechtVariantList
from modules.knecht_camera import KnechtImageCameraInfo
from modules.language import get_translation
from modules.log import init_logging

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


def get_queue(queue, timeout: int = 1) -> Optional[Union[str, dict, None]]:
    try:
        return queue.get(timeout=timeout)
    except Empty:
        pass


# noinspection PyUnresolvedReferences
class WolkeController(Thread):
    empty_model_index = QModelIndex()

    def __init__(self, app, exit_event: Event, connect_event: Event, disconnect_event: Event,
                 status_signal: Signal, connected_signal: Signal, disconnected_signal: Signal,
                 send_var_signal: Signal, transfer_signal: Signal):
        super(WolkeController, self).__init__()
        self.app = app

        self.exit_event = exit_event
        self.connect_event = connect_event
        self.disconnect_event = disconnect_event

        self.status_signal = status_signal
        self.connected_signal = connected_signal
        self.disconnected_signal = disconnected_signal
        self.send_variants = send_var_signal
        self.transfer_variants = transfer_signal

        self.in_queue = Queue()
        self.cmd_queue = Queue()

    def run(self):
        s = SocketProcess(self.app.logging_queue, self.in_queue, self.cmd_queue)

        while not self.exit_event.is_set():
            # -- Process incoming app events
            if self.connect_event.is_set():
                if not s.is_alive():
                    try:
                        s.start()
                    except SingleInstanceException:
                        self._socket_process_already_running()
                        continue
                self.connect_wolke()
            if self.disconnect_event.is_set():
                self.disconnect_wolke()

            # -- Process SocketIo Events
            event_contents = get_queue(self.in_queue)
            if event_contents:
                self._process_socketio_events(event_contents)

            self.exit_event.wait(2)

        self.cmd_queue.put(dict(cmd='shutdown'))

        if s.is_alive():
            s.join(timeout=5)

    def connect_wolke(self):
        self.cmd_queue.put(
            {'cmd': 'connect', 'data': {'host': KnechtSettings.wolke.get('host'),
                                        'port': KnechtSettings.wolke.get('port'),
                                        'user': KnechtSettings.wolke.get('user'),
                                        'token': KnechtSettings.wolke.get("token")}}
            )
        self.status_signal.emit(_('Verbinde mit {} als {}').format(KnechtSettings.wolke.get('host'),
                                                                   KnechtSettings.wolke.get("user")))
        self.connect_event.clear()

    def disconnect_wolke(self):
        self.cmd_queue.put({'cmd': 'disconnect'})
        self.disconnect_event.clear()

    def connect_failed(self):
        LOGGER.error('Error connecting to socketio Server: ')
        self.status_signal.emit(_('<b>Konnte nicht verbinden mit {}</b>').format(KnechtSettings.wolke.get('host')))
        self.status_signal.emit(
            _('Navigieren Sie zu Ihrer KnechtWolke Benutzer Profil and transferieren sie die '
              'Einstellungen hier. Prüfen Sie die korrekte Adresse eingegeben zu haben '
              'und das jener Server verfügbar ist von Ihrem lokalen Bereichsnetz. '
              'Tun Sie auch diese App zu Ihrer Feuerwalzenweißliste hinzu.'))

    def _socket_process_already_running(self):
        self.status_signal.emit(_('Ein SocketIO Prozess läuft bereits. Diese Anwendung schließen und '
                                  'eventuell hängende Instanzen unter TaskManager>Details>RenderKnecht.exe '
                                  'beenden.'))
        self.connect_event.clear()

    def _process_socketio_events(self, e: dict):
        event = e.get('event', '')
        data = e.get('data', dict())

        if event == 'connect':
            LOGGER.info('Connected to SocketIO Server')
            self.connected_signal.emit()
            self.status_signal.emit(_('Verbunden zum SteckbuchseReinRaus Server'))
        # -- Connect Failed
        elif event == 'connect_failed':
            self.connect_failed()
        # -- Disconnected
        elif event in ('disconnect_success', 'disconnect'):
            LOGGER.info('Disconnected from SocketIO Server.')
            self.disconnected_signal.emit()
            self.status_signal.emit(_('Verbindung getrennt.'))
        # -- Client Id created
        elif event == 'client_id_created':
            self.status_signal.emit(_('Verbunden als {}').format(data.get('id')))
        # -- Send PR-String
        elif event == 'send_pr_string':
            LOGGER.debug('Received PR-String send event with data: %s', data)
            self.send_pr_string(data)
        # -- Send PR-String
        elif event == 'send_pr_string_ave':
            LOGGER.debug('Received AVE PR-String send event with data: %s', data)
            self.send_pr_string(data, target_ave=True)
        # -- Transfer Preset
        elif event == 'transfer_presets':
            LOGGER.debug('Received Transfer Presets event with data: %s', data)
            self.transfer_presets(data)
        # -- Send Camera
        elif event == 'send_camera':
            LOGGER.info('Received Send Camera event with data: %s', data)
            self.send_camera(data)

    def transfer_presets(self, data: dict):
        url = f"{KnechtSettings.wolke.get('host')}:{KnechtSettings.wolke.get('port')}{data.get('url')}"
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

    def send_camera(self, data: dict):
        variants = KnechtVariantList()
        for camera_tag, value in data.items():
            if camera_tag in KnechtImageCameraInfo.rtt_camera_cmds:
                camera_cmd = KnechtImageCameraInfo.rtt_camera_cmds.get(camera_tag)
                camera_value = value.replace(' ', '')

                # - Filter 0 Clip values
                if camera_tag in ('knecht_clip_far', 'knecht_clip_near'):
                    if int(float(camera_value)) == 0:
                        continue

                # - Map values into camera-command
                try:
                    camera_cmd = camera_cmd.format(*camera_value.split(','))
                except Exception as e:
                    LOGGER.warning('Camera Info Tag Value does not match %s\n%s', camera_value, e)
                # - Add camera command to variants
                variants.add(self.empty_model_index, camera_tag, camera_cmd, 'camera_command')

        if variants.variants:
            self.status_signal.emit('Triggered camera send operation')
            self.send_variants.emit(variants)
        else:
            self.status_signal.emit(f'Received camera send event but found not enough camera info: {data}')

    def send_pr_string(self, data: dict, target_ave: bool = False):
        url = f"{KnechtSettings.wolke.get('host')}:{KnechtSettings.wolke.get('port')}{data.get('url')}"
        file_hash = data.get("hash")
        self.status_signal.emit(_('Erhielt Senden PR-String Ereignis mit Daten:') +
                                f'<br />{data.get("name")}<br />'
                                f'PR-String: {len(data.get("result").split("+"))}<br />'
                                f'File Hash: {file_hash}<br />'
                                f'File Url: {url}')

        file = None
        if not target_ave:
            file = self._get_plmxml(file_hash, url)
            if not file:
                return

        # -- Prepare Variants
        variants = self._get_knecht_variants(file, data)
        if target_ave:
            variants.ave = True

        # -- Send Variants
        if variants.variants:
            self.status_signal.emit('Triggered send operation')
            self.send_variants.emit(variants)

    def _get_knecht_variants(self, file: Optional[Path], preset_data: dict) -> KnechtVariantList:
        # -- Prepare Variants
        variants = KnechtVariantList()
        if file is not None:
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
