from datetime import datetime


class Job(object):
    """ Holds information about a render job """
    status_desc_list = ['Warteschlange', 'Szene wird vorbereitet',
                        'Rendering', 'Bilderkennung',
                        'Abgeschlossen', 'Fehlgeschlagen', 'Abgebrochen']
    combo_box_items = ['Zum Anfang der Warteschlange', 'Ans Ende der Warteschlange', 'Abbrechen']
    button_txt = 'Ausführen'

    def __init__(self, job_title, scene_file, render_dir, renderer,
                 ignore_hidden_objects='1', maya_delete_hidden='1', use_scene_settings='0',
                 client='Server'):
        self.title = job_title
        self.file = scene_file
        self.render_dir = render_dir
        self.renderer = renderer

        # CSB Import option ignoreHiddenObject
        self.ignore_hidden_objects = ignore_hidden_objects

        # Maya Layer Creation process optional argument
        self.maya_delete_hidden = maya_delete_hidden

        # Use render settings of the maya binary scene instead of creating
        self.use_scene_settings = use_scene_settings

        # Class version
        self.version = 2

        # Client hostname
        self.client = client

        # Creation time as datetime object
        self.created = datetime.now().timestamp()

        # Index in Service Manager Job queue
        self.remote_index = 0

        self.__img_num = 0
        self.total_img_num = 0
        self.__progress = 0

        # Status 0 - queue, 1 - scene editing, 2 - rendering, 3 - Image detection, 4 - finished, 5 - failed
        self.__status = 0
        self.status_name = self.status_desc_list[self.__status]
        self.in_progress = False

    @property
    def img_num(self):
        return self.__img_num

    @img_num.setter
    def img_num(self, val: int):
        """ Updating number of rendered images also updates progress """
        self.__img_num = val
        self.update_progress()

    @property
    def status(self):
        return self.__status

    @status.setter
    def status(self, status: int=0):
        if 0 < status < 4:
            self.in_progress = True
        elif 3 < status < 1:
            self.in_progress = False

        # Status failed/aborted
        if status > 4:
            self.progress = 0

        # Status finished
        if status == 4:
            self.progress = 100

        self.__status = status

        if status > len(self.status_desc_list):
            status_desc = 'Unbekannt'
        else:
            status_desc = self.status_desc_list[status]

        self.status_name = status_desc

    @property
    def progress(self):
        return self.__progress

    @progress.setter
    def progress(self, val: int):
        val = min(100, max(0, val))

        self.__progress = val

    def set_failed(self):
        self.progress = 0
        self.in_progress = False

        # Canceled jobs should not appear as failed
        if self.status != 6:
            self.status = 5

    def set_canceled(self):
        self.set_failed()
        self.status = 6

    def set_finished(self):
        if self.status >= 5:
            # Failed or aborted job can not be finished
            return

        self.progress = 100
        self.in_progress = False
        self.status = 4

    def update_progress(self):
        if self.status > 3:
            return

        # Display number of rendered images
        if self.status == 2:
            if self.img_num and self.total_img_num:
                self.status_name = '{0:03d}/{1:03d} Layer erstellt'.format(self.img_num, self.total_img_num)

                if self.renderer == 'arnold':
                    percent = min(100, max(0, self.img_num - 1) * 10)
                    self.status_name = f'Rendering {int(percent):02d}%'

        value = 0

        if self.total_img_num > 0:
            # Set job progress by number of created images
            value = (100 * max(1, self.img_num)) / max(1, self.total_img_num)
            # Add a 5% gap for image detection duration
            value = round(value * 0.95)

        self.progress = value
