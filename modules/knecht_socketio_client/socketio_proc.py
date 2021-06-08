import logging
import time
from multiprocessing import Process
from multiprocessing.queues import Queue
from queue import Empty
from typing import Optional, Union

import socketio

from .log import init_logging, setup_log_queue_listener, setup_logging
from modules.singleton import SingleInstance


def get_queue(queue, timeout: int = 1) -> Optional[Union[str, dict, None]]:
    try:
        return queue.get(timeout=timeout)
    except Empty:
        pass


class SocketProcess(Process):
    id, host, port, user, token = '', '', '', '', ''
    connect_timeout = 20.0  # Timeout between connection attempts
    last_connect = 0.0

    def __init__(self, log_queue: Queue, event_queue: Queue, incoming_queue: Queue):
        super(SocketProcess, self).__init__()
        self.event_queue = event_queue
        self.cmd_incoming_queue = incoming_queue

        self.logger = logging.getLogger(__name__)
        self.log_queue = log_queue

        self.sio = None

    def run(self):
        s = SingleInstance(flavor_id='knechtsocketioclient')  # will sys.exit(-1) if other instance is running

        self._logging_setup()

        # -- SocketIO Client --
        self.sio = socketio.Client()

        # -- Process incoming SocketIO Events
        self._setup_socketio_events()

        while 1:
            # -- Process incoming Events
            i = get_queue(self.cmd_incoming_queue)
            if i is None:
                continue

            if i.get('cmd') == 'shutdown':
                self.logger.debug('Shutdown CMD received.')
                self.disconnect_sio()
                break

            if i.get('cmd') == 'connect':
                self.logger.info('Connect CMD received.')
                i = i.get('data')
                self.host, self.port, self.user, self.token = i.get('host'), i.get('port'), i.get('user'), \
                                                              i.get('token')
                self.connect_sio()
                continue

            if i.get('cmd') == 'disconnect':
                self.logger.info('Disconnect CMD received.')
                self.disconnect_sio()

        self.logger.info('SocketIO process exiting.')
        logging.shutdown()
        self.log_listener.stop()

    def _logging_setup(self):
        # -- Init Logging
        setup_logging(self.log_queue)
        self.logger = init_logging(__name__)
        self.log_listener = setup_log_queue_listener(self.logger, self.log_queue)
        self.log_listener.start()
        self.logger.info('SocketIO process starting. Logger %s with handlers %s', self.logger.name,
                         self.logger.handlers)

    def _setup_socketio_events(self):
        @self.sio.on('connect')
        def on_connect():
            self.logger.info('Connected to SocketIO Server')
            self.event_queue.put(dict(event='connect', data=dict()))

        @self.sio.on('client_id_created')
        def on_client_id_created(data):
            self.id = data.get('id')
            self.event_queue.put(dict(event='client_id_created', data=data))

        @self.sio.on('disconnect')
        def on_disconnect():
            self.logger.info('Disconnected')
            self.event_queue.put(dict(event='disconnect', data=dict()))

        @self.sio.on('send_pr_string')
        def on_send_pr_string(data):
            self.logger.debug('Received PR-String send event with data: %s', data)
            self.event_queue.put(dict(event='send_pr_string', data=data))

        @self.sio.on('send_pr_string_ave')
        def on_send_pr_string_ave(data):
            self.logger.debug('Received PR-String AVE send event with data: %s', data)
            self.event_queue.put(dict(event='send_pr_string_ave', data=data))

        @self.sio.on('transfer_presets')
        def on_transfer_presets(data):
            self.logger.debug('Received Transfer Presets event with data: %s', data)
            self.event_queue.put(dict(event='transfer_presets', data=data))

        @self.sio.on('send_camera')
        def on_send_camera(data):
            self.logger.debug('Received Send Camera event with data: %s', data)
            self.event_queue.put(dict(event='send_camera', data=data))

    def _create_send_data(self, data: dict = None):
        send_data = {
            'app'  : 'RenderKnecht', 'user': self.user,
            'token': self.token}

        if data:
            send_data.update(data)
        return send_data

    def connect_sio(self):
        if time.time() - self.last_connect < self.connect_timeout:
            self.logger.info('Skipping repeated connection attempts until %.2fs within timeout.',
                             (time.time() - self.last_connect) - self.connect_timeout)
            return

        if not self.sio.connected:
            host = f"{self.host}:{self.port}"
            self.last_connect = time.time()

            try:
                self.sio.connect(host, headers=self._create_send_data())
            except Exception as e:
                self.logger.error('Error connecting to socketio Server: %s', e)
                self.event_queue.put(dict(event='connect_failed', data=dict()))

    def disconnect_sio(self):
        if self.sio.connected:
            self.sio.emit('client_disconnected', self._create_send_data())
            self.sio.disconnect()
            self.event_queue.put(dict(event='disconnect_success', data=dict()))
