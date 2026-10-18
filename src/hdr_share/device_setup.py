"""One-time device setup; only the signed VDD helper receives elevation."""
import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import uuid

from PySide6.QtCore import QThread, QTimer, QUrl, Signal, QEvent, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QFileDialog, QSizePolicy

from .devices import dependency_statuses, verify_package, DependencyStatus


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
    def __init__(self, component, report, archive=None):
        shell = C.WinDLL('shell32', use_last_error=True)
        shell.ShellExecuteExW.argtypes = [C.POINTER(ShellInfo)]
        shell.ShellExecuteExW.restype = W.BOOL
        self.kernel = C.WinDLL('kernel32', use_last_error=True)
        self.kernel.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
        self.kernel.GetExitCodeProcess.argtypes = [W.HANDLE, C.POINTER(W.DWORD)]
        self.kernel.CloseHandle.argtypes = [W.HANDLE]
        executable = str(Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe')
        arguments = subprocess.list2cmdline(['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
            str(resource_root() / 'scripts/setup-components.ps1'), '-Selected', component,
            '-ReportPath', str(report)] + (['-VddArchive', str(archive)] if archive else []))
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


def setup_directory():
    return Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'HDRScreenShare/setup'


def probe_dependencies():
    kernel = C.WinDLL('kernel32')
    kernel.GetTickCount64.restype = C.c_ulonglong
    boot_time = time.time() - kernel.GetTickCount64() / 1000
    reports = list(setup_directory().glob('*.json'))
    if getattr(sys, 'frozen', False):
        reports.extend(Path(sys.executable).parent.glob('setup-result*.json'))
    return dependency_statuses(reports=reports, boot_time=boot_time)


class DependencyProbe(QThread):
    def __init__(self, probe, parent=None):
        super().__init__(parent)
        self.probe = probe
        self.result = []

    def run(self):
        try:
            self.result = self.probe()
        except Exception as error:
            self.result = [DependencyStatus(key, name, 'error', f'Check failed: {error}')
                           for key, name in [('vdd', 'Virtual Display Driver'), ('vbcable', 'VB-CABLE')]]


class DeviceSetupDialog(QDialog):
    checked = Signal(object)

    def __init__(self, parent=None, *, before_install=lambda: True, mode='screen',
                 probe=probe_dependencies, installer_factory=ElevatedInstaller, report_dir=None):
        super().__init__(parent)
        self.setWindowTitle('Dependencies — HDR Screen Share')
        self.setMinimumWidth(560)
        self.before_install, self.mode = before_install, mode
        self.probe, self.installer_factory = probe, installer_factory
        self.report_dir = Path(report_dir) if report_dir is not None else setup_directory()
        self.installer = self.worker = None
        self.results = []
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        self.status = QLabel('Checking dependencies…')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        note = QLabel('Install only what you need. Virtual screen uses the display driver; '
                      'Application window uses VB-CABLE for audio. Python and app libraries are included.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.rows = {}
        self.display_button = QPushButton('Install virtual display')
        self.cable_button = QPushButton('Install VB-CABLE')
        self.install_buttons = {'vdd': self.display_button, 'vbcable': self.cable_button}
        self.links = {}
        for key, name, url in [
            ('vdd', 'Virtual Display Driver', 'https://github.com/VirtualDrivers/Virtual-Display-Driver/releases/tag/25.5.2'),
            ('vbcable', 'VB-CABLE', 'https://vb-audio.com/Cable/')]:
            row = QLabel(name + ' — Checking…')
            row.setTextFormat(Qt.TextFormat.PlainText)
            row.setWordWrap(True)
            layout.addWidget(row)
            self.rows[key] = row
            actions = QHBoxLayout()
            actions.addWidget(self.install_buttons[key])
            self.install_buttons[key].setEnabled(False)
            link = QPushButton('Download / instructions')
            link.clicked.connect(lambda checked=False, target=url: QDesktopServices.openUrl(QUrl(target)))
            actions.addWidget(link)
            self.links[key] = link
            layout.addLayout(actions)
        self.archive_button = QPushButton('Install downloaded VDD ZIP…')
        self.archive_button.setToolTip('Select Signed-Driver-v24.12.24-x64.zip from the linked release. '
                                       'This registers the dedicated display required by the app.')
        self.archive_button.clicked.connect(self.select_archive)
        layout.addWidget(self.archive_button)
        note = QLabel('Manual setup: extract VB-CABLE and run VBCABLE_Setup_x64.exe as administrator, '
                      'then restart Windows. For VDD, download Signed-Driver-v24.12.24-x64.zip and use '
                      '“Install downloaded VDD ZIP…” here. A generic VDD installation is not sufficient. '
                      'Keep headphones/speakers as the default sound output. VB-CABLE is donationware by VB-Audio.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.install_status = QLabel('Driver installation requires internet and Windows administrator approval.')
        self.install_status.setTextFormat(Qt.TextFormat.PlainText)
        self.install_status.setWordWrap(True)
        self.install_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.install_status)
        actions = QHBoxLayout()
        self.check_button = QPushButton('Check again')
        self.sound_button = QPushButton('Windows sound settings')
        self.close_button = QPushButton('Close')
        for button in (self.check_button, self.sound_button, self.close_button):
            actions.addWidget(button)
        layout.addLayout(actions)
        for label in self.findChildren(QLabel):
            label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self.display_button.clicked.connect(lambda: self.install_component('vdd'))
        self.cable_button.clicked.connect(lambda: self.install_component('vbcable'))
        self.check_button.clicked.connect(self.check)
        self.sound_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('ms-settings:sound')))
        self.close_button.clicked.connect(self.reject)
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.poll_install)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(5000)
        self.refresh_timer.timeout.connect(self.check_if_visible)
        self.refresh_timer.start()
        QTimer.singleShot(0, self.check)

    @property
    def busy(self):
        return self.installer is not None or (self.worker is not None and self.worker.isRunning())

    def check_if_visible(self):
        if self.isVisible() and self.isActiveWindow():
            self.check()

    def check(self):
        if self.installer is not None or self.worker is not None:
            return
        self.check_button.setEnabled(False)
        for button in self.install_buttons.values():
            button.setEnabled(False)
        self.archive_button.setEnabled(False)
        self.worker = DependencyProbe(self.probe, self)
        self.worker.finished.connect(self.finish_check)
        self.worker.start()

    def finish_check(self):
        worker, self.worker = self.worker, None
        worker.wait()
        self.results = worker.result
        worker.deleteLater()
        symbols = {'ready': '✓', 'missing': '✗', 'restart': '⚠', 'configure': '⚠', 'error': '⚠'}
        colors = {'ready': '#60d394', 'missing': '#ff8c8c'}
        for item in self.results:
            self.rows[item.component].setText(f'{symbols[item.state]} {item.name}\n{item.detail}')
            self.rows[item.component].setStyleSheet('color: ' + colors.get(item.state, '#f5cb71'))
            self.install_buttons[item.component].setEnabled(item.state == 'missing')
        self.archive_button.setEnabled(any(item.component == 'vdd' and item.state == 'missing' for item in self.results))
        self.status.setText('✓ All dependencies ready.' if all(item.ready for item in self.results)
                            else 'Some dependencies need attention. See the status for each mode below.')
        self.check_button.setEnabled(True)
        self.close_button.setEnabled(True)
        self.adjustSize()
        self.checked.emit(self.results)

    def select_archive(self):
        archive, _ = QFileDialog.getOpenFileName(self, 'Select signed VDD archive', '', 'ZIP archives (*.zip)')
        if archive:
            self.install_component('vdd', archive)

    def install_component(self, component, archive=None):
        if self.busy or self.worker is not None:
            return
        try:
            if not self.before_install():
                raise RuntimeError('Stop capture before installing drivers.')
            self.report_dir.mkdir(parents=True, exist_ok=True)
            self.report = self.report_dir / (component + '-' + uuid.uuid4().hex + '.txt')
            self.installer = (self.installer_factory(component, self.report, archive) if archive
                              else self.installer_factory(component, self.report))
            self.install_status.setText('Installing… Approve the Windows administrator prompt. '
                                       'Downloading and verifying the driver may take a few minutes.')
            for button in (*self.install_buttons.values(), self.archive_button, self.check_button, self.close_button):
                button.setEnabled(False)
            self.timer.start()
        except Exception as error:
            self.install_status.setText(f'Setup could not start: {error}. You can retry or use Download / instructions.')
            self.adjustSize()

    def poll_install(self):
        if self.installer is None:
            return
        try:
            code = self.installer.poll()
            if code is None:
                return
            self.timer.stop()
            self.installer = None
            try:
                message = self.report.read_text(encoding='utf-8-sig')
                completion = Path(str(self.report) + '.status').read_text().strip()
                if completion != 'ok' or code not in (0, 3010):
                    message = f'Setup failed (exit {code}).\n' + message
            except OSError:
                message = f'Setup ended without a completion report (exit {code}). Retry or use Download / instructions.'
            self.install_status.setText(message + f'\nReport: {self.report}')
            self.check()
        except Exception as error:
            self.timer.stop()
            # A failed poll must not allow a second elevated installer while the first may still run.
            self.install_status.setText(f'Cannot monitor setup: {error}. Check the report: {self.report}')
            self.timer.start()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow() and hasattr(self, 'worker'):
            self.check()

    def closeEvent(self, event):
        if self.busy or self.worker is not None:
            event.ignore()
        else:
            event.accept()

    def reject(self):
        if not self.busy and self.worker is None:
            super().reject()
