import re
from PyQt5.QtCore import QRunnable, pyqtSignal, QObject
from multiremodnav.call_remodnav import call_remodnav

class Signals(QObject):
    started = pyqtSignal(str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

class MultiRemodnavWorker(QRunnable):
    def __init__(self, data, batch_id):
        super(QRunnable, self).__init__()

        self.signals = Signals()
        self.data = data

        # regex data and save to class
        regex = re.findall("([0-9]*), (CC[0-9]..), (T[0-9]), ([a-zA-Z0-9]*)", data)

        self.row_id = regex[0][0]
        self.participant_id = regex[0][1]
        self.measurement_moment = regex[0][2]
        self.task_id = regex[0][3]
        self.starting_task = 1
        self.batch_id = batch_id
        
    def run(self):
        self.signals.started.emit(self.row_id)

        print("Thread start {}: {} {} {}".format(self.row_id, self.participant_id, self.measurement_moment, self.task_id))

        call_remodnav(self.participant_id, self.measurement_moment, self.task_id, self.batch_id)
        
        self.signals.finished.emit(self.row_id)