import datetime
import logging
import os
import shlex
from typing import List

from usb1 import USBContext

from core.configurations import Default
from core.managers import PythonADBManager
from data.models import Device, File, FileType
from helpers.converters import __converter_to_permissions_default__
from services.adb import ShellCommand


class FileRepository:
    @classmethod
    def file(cls, path: str) -> (File, str):
        if not PythonADBManager.device:
            return None, "No device selected!"
        if not PythonADBManager.device.available:
            return None, "Device not available!"
        try:
            path = PythonADBManager.clear_path(path)
            mode, size, mtime = PythonADBManager.device.stat(path.replace(' ', r'\ '))
            file = File(
                name=os.path.basename(os.path.normpath(path)),
                size=size,
                date_time=datetime.datetime.utcfromtimestamp(mtime),
                permissions=__converter_to_permissions_default__(list(oct(mode)[2:]))
            )

            if file.type == FileType.LINK:
                args = ShellCommand.LS_LIST_DIRS + [path.replace(' ', r'\ ') + '/']
                response = PythonADBManager.device.shell(shlex.join(args))
                file.link_type = FileType.UNKNOWN
                if response and response.startswith('d'):
                    file.link_type = FileType.DIRECTORY
                elif response and response.__contains__('Not a'):
                    file.link_type = FileType.FILE
            file.path = path
            return file, None

        except BaseException as error:
            logging.error(f"Unexpected {error=}, {type(error)=}")
            return None, error

    @classmethod
    def files(cls) -> (List[File], str):
        if not PythonADBManager.device:
            return None, "No device selected!"
        if not PythonADBManager.device.available:
            return None, "Device not available!"

        files = []
        try:
            path = PythonADBManager.path()
            response = PythonADBManager.device.list(path.replace(' ', r'\ '))

            args = ShellCommand.LS_ALL_DIRS + [path.replace(' ', r'\ ') + "*/"]
            dirs = PythonADBManager.device.shell(" ".join(args)).split()

            for file in response:
                if file.filename.decode() == '.' or file.filename.decode() == '..':
                    continue

                permissions = __converter_to_permissions_default__(list(oct(file.mode)[2:]))
                link_type = None
                if permissions[0] == 'l':
                    link_type = FileType.FILE
                    if dirs.__contains__(f"{path}{file.filename.decode()}/"):
                        link_type = FileType.DIRECTORY

                files.append(
                    File(
                        name=file.filename.decode(),
                        size=file.size,
                        path=f"{path}{file.filename.decode()}",
                        link_type=link_type,
                        date_time=datetime.datetime.utcfromtimestamp(file.mtime),
                        permissions=permissions,
                    )
                )

            return files, None

        except BaseException as error:
            logging.error(f"Unexpected {error=}, {type(error)=}")
            return files, error

    @classmethod
    def download(cls, progress_callback: callable, source: str) -> (str, str):
        destination = Default.device_downloads_path(PythonADBManager.get_device())
        return cls.download_to(progress_callback, source, destination)

    class UpDownHelper:
        def __init__(self, callback: callable):
            self.callback = callback
            self.written = 0
            self.total = 0

        def call(self, path: str, written: int, total: int):
            if self.total != total:
                self.total = total
                self.written = 0

            self.written += written
            self.callback(path, int(self.written / self.total * 100))

    @classmethod
    def download_to(cls, progress_callback: callable, source: str, destination: str) -> (str, str):
        helper = cls.UpDownHelper(progress_callback)
        destination = os.path.join(destination, os.path.basename(os.path.normpath(source)))
        if PythonADBManager.device and PythonADBManager.device.available and source:
            try:
                PythonADBManager.device.pull(
                    device_path=source,
                    local_path=destination,
                    progress_callback=helper.call
                )
                return f"Download successful!\nDest: {destination}", None
            except BaseException as error:
                logging.error(f"Unexpected {error=}, {type(error)=}")
                return None, error
        return None, None

    @classmethod
    def new_folder(cls, name) -> (str, str):
        if not PythonADBManager.device:
            return None, "No device selected!"
        if not PythonADBManager.device.available:
            return None, "Device not available!"

        try:
            args = [ShellCommand.MKDIR, f'{PythonADBManager.path()}{name}'.replace(' ', r"\ ")]
            response = PythonADBManager.device.shell(shlex.join(args))
            return None, response

        except BaseException as error:
            logging.error(f"Unexpected {error=}, {type(error)=}")
            return None, error

    @classmethod
    def upload(cls, progress_callback: callable, source: str) -> (str, str):
        helper = cls.UpDownHelper(progress_callback)
        destination = PythonADBManager.path() + os.path.basename(os.path.normpath(source))
        if PythonADBManager.device and PythonADBManager.device.available and PythonADBManager.path() and source:
            try:
                PythonADBManager.device.push(
                    local_path=source,
                    device_path=destination,
                    progress_callback=helper.call
                )
                return f"Upload successful!\nDest: {destination}", None
            except BaseException as error:
                logging.error(f"Unexpected {error=}, {type(error)=}")
                return None, error
        return None, None


class DeviceRepository:
    @classmethod
    def devices(cls) -> (List[Device], str):
        if PythonADBManager.device:
            PythonADBManager.device.close()

        errors = []
        devices = []
        for device in USBContext().getDeviceList(skip_on_error=True):
            for setting in device.iterSettings():
                if (setting.getClass(), setting.getSubClass(), setting.getProtocol()) == (0xFF, 0x42, 0x01):
                    try:
                        PythonADBManager.connect(device.getSerialNumber())
                        device_id = device.getSerialNumber()
                        device_name = " ".join(
                            PythonADBManager.device.shell(" ".join(ShellCommand.GETPROP_PRODUCT_MODEL)).split()
                        )
                        device_type = "device" if PythonADBManager.device.available else "unknown"
                        devices.append(Device(id=device_id, name=device_name, type=device_type))
                        PythonADBManager.device.close()
                    except BaseException as error:
                        logging.error(f"Unexpected {error=}, {type(error)=}")
                        errors.append(str(error))

        return devices, str("\n".join(errors))

    @classmethod
    def connect(cls, device_id: str) -> (str, str):
        try:
            if PythonADBManager.device:
                PythonADBManager.device.close()
            PythonADBManager.connect(device_id)
            if PythonADBManager.device.available:
                device_name = " ".join(
                    PythonADBManager.device.shell(" ".join(ShellCommand.GETPROP_PRODUCT_MODEL)).split()
                )
                PythonADBManager.set_device(Device(id=device_id, name=device_name, type="device"))
                return "Connection established", None
            return None, "Device not available"

        except BaseException as error:
            logging.error(f"Unexpected {error=}, {type(error)=}")
            return None, error

    @classmethod
    def disconnect(cls) -> (str, str):
        try:
            if PythonADBManager.device:
                PythonADBManager.device.close()
                return "Disconnected", None
            return None, None
        except BaseException as error:
            logging.error(f"Unexpected {error=}, {type(error)=}")
            return None, error
