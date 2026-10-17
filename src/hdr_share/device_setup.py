"""One-time device setup; only the signed VDD helper receives elevation."""
import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
import uuid

from PySide6.QtCore import QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout

from .devices import check_devices, verify_package
from .virtual_display import WindowsDisplayBackend


def resource_root():
    return Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[2]


def fetch_vdd(destination, descriptor, *, opener=None):
    if opener is None:
        opener = lambda url: urllib.request.urlopen(url, timeout=30)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + '.' + uuid.uuid4().hex + '.partial')
    try:
        with opener(descriptor['url']) as response, temporary.open('wb') as output:
            total = 0
            while block := response.read(65536):
                total += len(block)
                if total > 16 * 1024 * 1024:
                    raise RuntimeError('Unexpected driver package size')
                output.write(block)
        verify_package(temporary, descriptor['sha256'], set(descriptor['required']))
        temporary.replace(destination)
        return destination
    finally:
        temporary.unlink(missing_ok=True)


class ShellInfo(C.Structure):
    _fields_ = [('size', W.DWORD), ('mask', W.ULONG), ('hwnd', W.HWND),
                ('verb', W.LPCWSTR), ('file', W.LPCWSTR), ('parameters', W.LPCWSTR),
                ('directory', W.LPCWSTR), ('show', C.c_int), ('instance', W.HINSTANCE),
                ('id_list', W.LPVOID), ('class_name', W.LPCWSTR), ('class_key', W.HKEY),
                ('hot_key', W.DWORD), ('icon', W.HANDLE), ('process', W.HANDLE)]


class ElevatedInstaller:
    def __init__(self, archive):
        shell = C.WinDLL('shell32', use_last_error=True)
        shell.ShellExecuteExW.argtypes = [C.POINTER(ShellInfo)]
        shell.ShellExecuteExW.restype = W.BOOL
        self.kernel = C.WinDLL('kernel32', use_last_error=True)
        self.kernel.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
        self.kernel.GetExitCodeProcess.argtypes = [W.HANDLE, C.POINTER(W.DWORD)]
        self.kernel.CloseHandle.argtypes = [W.HANDLE]
        executable = str(Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe')
        arguments = subprocess.list2cmdline(['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
            str(resource_root() / 'scripts/install-devices.ps1'), '-VddArchive', str(archive)])
        info = ShellInfo(size=C.sizeof(ShellInfo), mask=0x40, verb='runas',
                         file=executable, parameters=arguments, show=0)
        if not shell.ShellExecuteExW(C.byref(info)):
            raise C.WinError(C.get_last_error())
        self.handle = info.process

    def poll(self):
        if self.kernel.WaitForSingleObject(self.handle, 0) == 258:
            return None
        code = W.DWORD()
        if not self.kernel.GetExitCodeProcess(self.handle, C.byref(code)):
            raise C.WinError(C.get_last_error())
        self.kernel.CloseHandle(self.handle)
        self.handle = None
        return code.value


class DriverDownload(QThread):
    downloaded = Signal(str)
    failed = Signal(str)

    def run(self):
        try:
            descriptor = json.loads((resource_root() / 'scripts/device-packages.json').read_text())['vdd']
            cache = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'HDRScreenShare/downloads/vdd-signed-x64.zip'
            self.downloaded.emit(str(fetch_vdd(cache, descriptor)))
        except Exception as error:
            self.failed.emit(str(error))


class DeviceSetupDialog(QDialog):
    def __init__(self, parent=None, *, before_install=lambda: True, mode='screen'):
        super().__init__(parent)
        self.setWindowTitle('Devices')
        self.setMinimumWidth(480)
        self.before_install = before_install
        self.mode = mode
        self.download = self.installer = None
        layout = QVBoxLayout(self)
        self.status = QLabel('')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.display_button = QPushButton('Install virtual display')
        self.cable_button = QPushButton('Get VB-CABLE (window mode)')
        self.cable_button.setVisible(mode == 'application')
        self.check_button = QPushButton('Refresh')
        for button in (self.display_button, self.cable_button, self.check_button):
            layout.addWidget(button)
        note = QLabel('Install once, then share in Discord.' if mode == 'screen' else
                      'Window audio uses VB-CABLE. Keep your headphones as the default output.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.display_button.clicked.connect(self.start_download)
        self.cable_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('https://vb-audio.com/Cable/')))
        self.check_button.clicked.connect(self.check)
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.poll_install)
        self.check()

    def check(self):
        result = check_devices(require_audio=self.mode == 'application')
        self.status.setText('Devices ready' if result.ready else '\n'.join(result.issues))
        self.display_button.setEnabled(WindowsDisplayBackend().owned_display() is None)

    def start_download(self):
        self.display_button.setEnabled(False)
        self.status.setText('Downloading display driver…')
        self.download = DriverDownload(self)
        self.download.downloaded.connect(self.start_installer)
        self.download.failed.connect(self.failed)
        self.download.start()

    def failed(self, message):
        self.status.setText('Setup failed: ' + message)
        self.display_button.setEnabled(True)

    def start_installer(self, archive):
        try:
            if not self.before_install():
                raise RuntimeError('Stop capture first')
            self.installer = ElevatedInstaller(archive)
            self.status.setText('Installing virtual display…')
            self.timer.start()
        except Exception as error:
            self.failed(str(error))

    def poll_install(self):
        try:
            code = self.installer.poll()
            if code is None:
                return
            self.timer.stop()
            self.installer = None
            if code:
                self.failed(f'Installer exit code {code}. Log: %LOCALAPPDATA%/HDRScreenShare/device-install.log')
            else:
                backend = WindowsDisplayBackend()
                if backend.owned_display() is not None:
                    backend.detach_initial_output()
                self.check()
        except Exception as error:
            self.timer.stop()
            self.failed(str(error))

    def closeEvent(self, event):
        if (self.download is not None and self.download.isRunning()) or self.installer is not None:
            event.ignore()
        else:
            event.accept()

    def reject(self):
        if not ((self.download is not None and self.download.isRunning()) or self.installer is not None):
            super().reject()
