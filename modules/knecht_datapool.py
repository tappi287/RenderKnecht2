import datetime
import logging
import sys
from threading import Event, Thread
from typing import List, Tuple

# noinspection PyPackageRequirements
import mysql.connector
from PySide2.QtCore import QObject, Signal
# noinspection PyPackageRequirements
from mysql.connector import errorcode as my_sql_error_code

from modules.language import get_translation
from modules.log import init_logging
from modules.settings import KnechtSettings

LOGGER = init_logging(__name__)

# translate strings
lang = get_translation()
lang.install()
_ = lang.gettext


class DatapoolConnector:
    tables = {
        "project": {
            "table": "`Projekt`",
            "condition": "WHERE `aktiv` > 0 AND `finished` = 0",
            "order": "ORDER BY `reihenfolge`",
            "columns": "`bezeichnung`, `id`, `modelyear`, `jobNummer`",
            },
        "image": {
            'table': "`Bild`",
            "condition": "WHERE `projektID` = {project_id}",
            "order": "ORDER BY `erstellt` DESC",
            "columns": "`bezeichnung`, `id`, `prio`, `erstellt`, `vorbereitungsString`, "
                       "`wagenBauteilID`, `producedBildID`",
            },
        "image_opt": {
            "table": "`WagenBauteil`",
            "condition": "WHERE `id` = {opt_id}",
            "columns": "`bezeichnung`, `id`, `pr`, `paket`, `kategorie`, `collage`",
            },
        "opt_derivate": {
            "table": "`NMWagenBauteilWagenModel`",
            "condition": "WHERE `wagenBauteilId` = {opt_id}",
            "columns": "`wagenModelId`",
            },
        "single_derivate": {
            "table": "`WagenModel`",
            "condition": "WHERE `id` = {derivate_id}",
            "columns": "`bezeichnung`",
            },
        "model": {
            "table": "`WagenFamilie`",
            "columns": "`bezeichnung`, `id`",
            },
        "derivate": {
            "table": "`WagenModel`",
            "order": "ORDER BY `reihenfolge`",
            "columns": "`bezeichnung`, `id`, `wagenFamilieID`",
            },
        }

    def __init__(self, config: dict):
        # --- config ---
        # config should contain dict(
        # host=*, user=*, password=*, database=*,
        self.config = config

        # --- attrib ---
        self._error_msg = str()
        self.data = dict()
        for key in self.tables.keys():
            self.data[key] = dict()

        # --- MySql Connector object ---
        # Dummy object until we connect
        self.db = mysql.connector.connection.MySQLConnection

    def connect_db(self) -> bool:
        """ Establish physical connection to the database
        :return: connection success, call error_report() if this returns False
        """
        if not self.config:
            self._error_msg = _('Keine Datenbankkonfiguration verfügbar. Datapool über das Netzwerk erreichbar?')
            return False

        try:
            self.db = mysql.connector.connect(**self.config)
            LOGGER.info('Connecting to database: %s', self.config.get('host'))
        except mysql.connector.Error as err:
            self._set_connection_error(err)
            return False

        if not self.db.is_connected():
            return False

        return True

    def _query(self, query: str, fetch_one: bool=False, fetch_num: int=0) -> List[Tuple]:
        try:
            cur = self.db.cursor()
        except mysql.connector.OperationalError as err:
            self._set_sql_error(err, query)
            return list()

        try:
            cur.execute(query)
        except mysql.connector.Error as err:
            self._set_sql_error(err, query)
            return list()

        if not fetch_one and not fetch_num:
            result = cur.fetchall()
        elif not fetch_one and fetch_num > 0:
            result = cur.fetchmany(size=fetch_num)
        elif fetch_one and not fetch_num:
            result = cur.fetchone()

        cur.close()
        return result

    @staticmethod
    def _create_query(table, columns, *args):
        query = f'SELECT {columns or "*"} FROM {table}'
        for part in args:
            if part:
                query += f' {part}'
        return f'{query};'

    def _create_image_name(self, category, derivate_name, pr_name, pr, pkg, project_id):
        model_year = self.data['project'].get(project_id)
        if model_year:
            model_year = model_year[1] or "0000"
        else:
            model_year = "0000"

        img_name = f'{category}_{derivate_name}_{model_year}_{pr_name}_'
        for part in (pr, pkg):
            if part:
                img_name += f'{part}-'

        return img_name[:-1].replace(' ', '-')

    def collect_projects(self) -> bool:
        """ Read available, active projects and store in self.data
            -> ['project'][integer id] = (name, model year, job)
        """
        p = self.tables.get('project') or dict()
        query = self._create_query(p.get('table'), p.get('columns'), p.get('condition'), p.get('order'))

        db_result = self._query(query)

        if not db_result:
            return False

        project_data = {'project': dict()}
        for (name, _id, model_year, job) in db_result:
            project_data['project'][_id] = (name, model_year, job)

        self.data.update(project_data)
        return True

    def collect_images(self, project_id: int) -> bool:
        """ Read images and image-options "wagenbauteil" for given project identifier

        :param int project_id: project identifier
        :return:
        """
        i = self.tables.get('image') or dict()
        condition = i.get('condition') or ''
        condition = condition.format(project_id=project_id)

        query = self._create_query(i.get('table'), i.get('columns'), condition, i.get('order'))
        db_result = self._query(query)

        if not db_result:
            return False

        image_data = {'image': {project_id: dict()}}
        for (pr_name, _id, priority, created, pr_string, opt_id, produced_image_id) in db_result:
            opt_name, _, pr, pkg, category, collage = self.collect_image_options(opt_id)

            for derivate_name in self.collect_derivates_from_opt_id(opt_id):
                img_name = self._create_image_name(category, derivate_name, pr_name, pr, pkg, project_id)
                image_data['image'][project_id][_id] = (img_name, priority, created,
                                                        pr_string, opt_id, produced_image_id)

        self.data.update(image_data)
        return True

    def collect_derivates_from_opt_id(self, opt_id: int) -> List[str]:
        """ Read which derivates belong to which "wagenbauteil"
            -> [derivate names]
        :param list opt_id: List of derivate names
        :return:
        """
        o = self.tables.get('opt_derivate')
        condition = o.get('condition') or ''
        condition = condition.format(opt_id=opt_id)

        query = self._create_query(o.get('table'), o.get('columns'), condition)
        db_result = self._query(query)

        result = list()

        for row in db_result:
            derivate_name = self.collect_single_derivate_by_id(row[0])
            if derivate_name:
                result.append(derivate_name)

        return result

    def collect_single_derivate_by_id(self, derivate_id) -> str:
        d = self.tables.get('single_derivate') or dict()
        condition = d.get('condition') or ''
        condition = condition.format(derivate_id=derivate_id)

        query = self._create_query(d.get('table'), d.get('columns'), condition)
        db_result = self._query(query, fetch_one=True)

        return db_result[0] or ''

    def collect_image_options(self, opt_id: int) -> Tuple[str, int, str, str, str, int]:
        """ Read corresponding "wagenbauteil" row for current image
            -> (name, identifier, pr option, package, category, collage bool as int)

        :param int opt_id: "wagenbauteil" identifier
        :return:
        """
        name, _id, pr, package, category, collage = '', int(), '', '', '', int()

        o = self.tables.get('image_opt') or dict()

        condition = o.get('condition') or ''
        condition = condition.format(opt_id=opt_id)

        query = self._create_query(o.get('table'), o.get('columns'), condition)
        db_result = self._query(query, fetch_one=True)

        if db_result:
            name, _id, pr, package, category, collage = db_result

        return name, _id, pr, package, category, collage

    def _set_connection_error(self, err: mysql.connector.Error):
        msg = _('Datenbank Fehler:\n')
        LOGGER.error("Error connecting MySql: %s %s", err.errno, err)

        if err.errno in (my_sql_error_code.ER_ACCESS_DENIED_ERROR, my_sql_error_code.CR_CONN_HOST_ERROR):
            msg += _('Kann keine Verbindung zur Datenbank herstellen!\n{}')
        elif err.errno == my_sql_error_code.ER_BAD_DB_ERROR:
            msg += _('Kann Datenbank nicht finden!\n{}')
        else:
            msg += _('Unbekannter Fehler:\n{}')

        self._error_msg = msg.format(err)

    def _set_sql_error(self, err: mysql.connector.Error, query: str=''):
        msg = _('Datenbank Fehler:\n')
        err_msg = f'SQLSTATE: {err.sqlstate}, Error Code: {err.errno}, Message: {err.msg}, Query: {query or ""}'
        LOGGER.error(err_msg)
        self._error_msg = msg + err_msg

    def error_report(self) -> str:
        if not self._error_msg:
            return _('Die Anfrage an die Datenbank resultierte in keinem Ergebnis.')
        return self._error_msg

    def close(self):
        try:
            self.db.close()
        except Exception as e:
            LOGGER.error(e)


class DatapoolThread(Thread):

    def __init__(self, controller):
        """ Thread fetching data from the database and forwarding it via
            Controller signals.

        :param DatapoolController controller:
        :param db_config:
        """
        super(DatapoolThread, self).__init__()
        self.controller = controller
        self.db = None

        self.exit_event = Event()
        self.project_requested = -1

    def run(self) -> None:
        self.db = DatapoolConnector(KnechtSettings.load_db_config())

        # Connect to database
        LOGGER.debug('Connecting to database')
        if not self.db.connect_db():
            self.error(self.db.error_report())
            self.shutdown()
            return

        # Get Project Data
        if not self.db.collect_projects():
            self.error(self.db.error_report())
            self.shutdown()
            return

        # Send Project Data
        LOGGER.debug('Found datapool project data of size: %s', len(self.db.data['project']))
        self.controller.add_projects.emit(self.db.data['project'])

        # Loop and wait for project request
        while not self.exit_event.is_set():
            if self.project_requested != -1:
                project_id = self.project_requested

                if not self.db.collect_images(project_id):
                    self.error(self.db.error_report())
                    self.db.data['image'][project_id] = dict()

                for img_id in self.db.data['image'][project_id]:
                    # Convert to String data
                    img_data = list()
                    for d in self.db.data['image'][project_id][img_id]:
                        if type(d) == datetime.datetime:
                            d = d.strftime('%d.%m.%y %H:%M')
                        img_data.append(str(d))

                    self.db.data['image'][project_id][img_id] = tuple(img_data)

                """ (name, priority, created, pr_string, opt_id, produced_image_id) """
                LOGGER.debug('Transmitting datapool image data of size: %s', len(self.db.data['image'][project_id]))

                self.controller.add_images.emit(self.db.data['image'][project_id])
                self.project_requested = -1

            self.exit_event.wait(timeout=0.8)

        self.shutdown()

    def request_project(self, project_id: int):
        self.project_requested = project_id

    def error(self, error_msg):
        self.controller.error.emit(error_msg)

    def shutdown(self):
        self.exit_event.set()

        if self.db:
            self.db.close()


class DatapoolController(QObject):
    error = Signal(str)
    add_projects = Signal(dict)
    add_images = Signal(dict)

    def __init__(self, parent):
        super(DatapoolController, self).__init__(parent)
        self.parent = parent
        self.db_thread = DatapoolThread(self)

        self.destroyed.connect(self.close)

    def start(self):
        self.db_thread.start()

    def close(self) -> bool:
        if self.db_thread.is_alive():
            LOGGER.info('Shutting down Datapool Connection Thread.')
            self.db_thread.shutdown()
            self.db_thread.join(timeout=2)

            if self.db_thread.is_alive():
                LOGGER.error("Datapool thread could not be joined. Network trouble. We depend on Windows now, "
                             "aka we're lost.")
                self.error.emit(_('Netzwerkverbindung konnte nicht beendet werden. Bitte warten und in einer Minute '
                                  'erneut versuchen.'))
                return False

        return True

    def request_project(self, project_id: str):
        self.db_thread.request_project(int(project_id))


def _shutdown(db: DatapoolConnector):
    db.close()
    del db

    sys.exit()


def _main():
    logging.basicConfig()
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    local_dev_config = {
        'host': "localhost", 'user': 'dev', 'password': 'y$=oAQX.x4oWh2%', 'database': 'dev'
        }

    db = DatapoolConnector(local_dev_config)
    if not db.connect_db():
        logger.debug(db.error_report())
        _shutdown(db)

    logger.debug('Successfully connected!')

    if not db.collect_projects():
        _shutdown(db)

    for _id in db.data.get('project'):
        logger.debug('Project %s: %s', _id, db.data['project'].get(_id))

    project_id = int(input("Enter a project id: "))

    if not db.collect_images(project_id):
        _shutdown(db)

    for img_id in db.data['image'][project_id]:
        name, priority, created, pr_string, opt_id, produced_image_id = db.data['image'][project_id][img_id]
        logger.debug('%s - %s - %s', name, created, priority)

    _shutdown(db)


if __name__ == '__main__':
    _main()
