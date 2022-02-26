import logging
import os
import subprocess

from PyQt5 import QtCore
from PyQt5.QtCore import QThread, QObject
from PyQt5.QtWidgets import QWidget
from adb_shell.auth.keygen import keygen
from adb_shell.auth.sign_pythonrsa import PythonRSASigner

from data.models import MessageData


class CommonProcess:
    def __init__(self, arguments: list, stdout=subprocess.PIPE, stdout_callback: callable = None):
        if arguments and len(arguments) > 0:
            try:
                process = subprocess.Popen(arguments, stdout=stdout, stderr=subprocess.PIPE)
                if stdout == subprocess.PIPE and stdout_callback:
                    for line in iter(process.stdout.readline, b''):
                        stdout_callback(line.decode(encoding='utf-8'))
                data, error = process.communicate()
                self.ExitCode: int = process.poll()
                self.IsSuccessful: bool = process.poll() == 0
                self.ErrorData: str = error.decode(encoding='utf-8')
                self.OutputData: str = data.decode(encoding='utf-8') if data else None
            except BaseException as error:
                logging.exception(f"Unexpected {error=}, {type(error)=}")
                self.ErrorData = str(error)


class AsyncRepositoryWorker(QThread):
    on_response = QtCore.pyqtSignal(object, object)  # Response : data, error

    def __init__(
            self, worker_id: int, name: str,
            repository_method: callable,
            arguments: tuple, response_callback: callable
    ):
        super(AsyncRepositoryWorker, self).__init__()
        self.on_response.connect(response_callback)
        self.finished.connect(self.close)

        self.__repository_method = repository_method
        self.__arguments = arguments
        self.loading_widget = None
        self.closed = False
        self.id = worker_id
        self.name = name

    def run(self):
        data, error = self.__repository_method(*self.__arguments)
        self.on_response.emit(data, error)

    def close(self):
        if self.loading_widget:
            self.loading_widget.close()
        self.deleteLater()
        self.closed = True

    def set_loading_widget(self, widget: QWidget):
        self.loading_widget = widget

    def update_loading_widget(self, path, progress):
        if self.loading_widget and not self.closed:
            self.loading_widget.update_progress(f"SOURCE: {path}", progress)


class ProgressCallbackHelper(QObject):
    progress_callback = QtCore.pyqtSignal(str, int)

    def setup(self, parent: QObject, callback: callable):
        self.setParent(parent)
        self.progress_callback.connect(callback)


class Communicate(QObject):
    files = QtCore.pyqtSignal()
    devices = QtCore.pyqtSignal()

    up = QtCore.pyqtSignal()
    files__refresh = QtCore.pyqtSignal()
    path_toolbar__refresh = QtCore.pyqtSignal()

    status_bar = QtCore.pyqtSignal(str, int)  # Message, Duration
    notification = QtCore.pyqtSignal(MessageData)


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


def get_python_rsa_keys_signer(rerun=True) -> PythonRSASigner:
    key = os.path.expanduser('~/.android/adbkey')
    if os.path.isfile(key):
        with open(key) as f:
            private = f.read()
        with open(key + '.pub') as f:
            public = f.read()
        return PythonRSASigner(public, private)
    elif rerun:
        path = os.path.expanduser('~/.android')
        if not os.path.isfile(path):
            if not os.path.isdir(path):
                os.mkdir(path)
            keygen(key)
            return get_python_rsa_keys_signer(False)
