"""Small parent-process watchdog; never starts capture or audio."""
import ctypes as C
from ctypes import wintypes as W
from dataclasses import asdict
import json
import logging
import os
import subprocess
import sys
import time
import base64
from pathlib import Path
import uuid

from .virtual_display import DisplayLeaseError, DisplayState, WindowsDisplayBackend


def device_kernel():
    kernel = kernel_api()
    kernel.CreateEventW.argtypes = [W.LPVOID, W.BOOL, W.BOOL, W.LPCWSTR]
    kernel.CreateEventW.restype = W.HANDLE
    kernel.OpenEventW.argtypes = [W.DWORD, W.BOOL, W.LPCWSTR]
    kernel.OpenEventW.restype = W.HANDLE
    kernel.SetEvent.argtypes = [W.HANDLE]
    kernel.GetExitCodeProcess.argtypes = [W.HANDLE, C.POINTER(W.DWORD)]
    kernel.WaitForMultipleObjects.argtypes = [W.DWORD, C.POINTER(W.HANDLE), W.BOOL, W.DWORD]
    kernel.WaitForMultipleObjects.restype = W.DWORD
    return kernel


def control_owned_device(enabled):
    """Only the pinned dedicated adapter; never a wildcard or a caller-supplied ID."""
    from .virtual_display import OWN_INSTANCE, owned_device_registered
    if not owned_device_registered():
        raise DisplayLeaseError('Owned virtual adapter validation failed')
    command = Path(os.environ['SystemRoot']) / 'System32' / 'pnputil.exe'
    result = subprocess.run([str(command), '/enable-device' if enabled else '/disable-device',
                             OWN_INSTANCE], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
                            timeout=20)
    if result.returncode != 0:
        raise DisplayLeaseError(f'Virtual adapter operation failed: {result.returncode}; {result.stdout!r}; {result.stderr!r}')


def remove_owned_device():
    # Stay alive after parent death as well: a transient PnP failure must not
    # orphan the monitor. The parent keeps its lease until this helper exits.
    while True:
        try:
            control_owned_device(False)
            return
        except (OSError, subprocess.SubprocessError, DisplayLeaseError):
            logging.exception('Virtual adapter removal failed; retrying')
            time.sleep(1)


def claim_cleanup_lease(backend, kernel, deferred):
    while True:
        try:
            backend.claim()
            return
        except DisplayLeaseError:
            # A new session may still be awaiting UAC, so it has not necessarily
            # established its own watchdog. Keep cleanup responsibility alive.
            kernel.SetEvent(deferred)
            time.sleep(.1)


class ShellExecuteInfo(C.Structure):
    _fields_ = [('size', W.DWORD), ('mask', W.ULONG), ('hwnd', W.HWND),
                ('verb', W.LPCWSTR), ('file', W.LPCWSTR), ('parameters', W.LPCWSTR),
                ('directory', W.LPCWSTR), ('show', C.c_int), ('instance', W.HINSTANCE),
                ('id_list', W.LPVOID), ('class_name', W.LPCWSTR), ('class_key', W.HKEY),
                ('hotkey', W.DWORD), ('icon', W.HANDLE), ('process', W.HANDLE)]


class ElevatedDisplayGuard:
    """One UAC-approved session enables the adapter and removes it on parent exit."""
    def __init__(self, *, launch=False):
        self.kernel = device_kernel()
        self.ready = self.stop = self.process = self.failed = self.deferred = None
        if launch:
            self.start()

    def start(self):
        nonce = uuid.uuid4().hex
        try:
            self.ready = self.kernel.CreateEventW(None, True, False, f'Local\\HDRScreenShare.Ready.{nonce}')
            self.stop = self.kernel.CreateEventW(None, True, False, f'Local\\HDRScreenShare.Stop.{nonce}')
            self.failed = self.kernel.CreateEventW(None, True, False, f'Local\\HDRScreenShare.Failed.{nonce}')
            self.deferred = self.kernel.CreateEventW(None, True, False, f'Local\\HDRScreenShare.Deferred.{nonce}')
            if not self.ready or not self.stop or not self.failed or not self.deferred:
                raise C.WinError(C.get_last_error())
            parent = self.kernel.OpenProcess(0x1000, False, os.getpid())
            if not parent:
                raise C.WinError(C.get_last_error())
            try:
                birth = creation_time(self.kernel, parent)
            finally:
                self.kernel.CloseHandle(parent)
            payload = base64.urlsafe_b64encode(json.dumps(
                {'pid': os.getpid(), 'birth': birth, 'nonce': nonce}).encode()).decode()
            executable = Path(sys.executable)
            if not getattr(sys, 'frozen', False):
                executable = executable.with_name('pythonw.exe')
            arguments = ([] if getattr(sys, 'frozen', False) else ['-m', 'hdr_share'])
            arguments += ['--device-guard', payload]
            shell = C.WinDLL('shell32', use_last_error=True)
            shell.ShellExecuteExW.argtypes = [C.POINTER(ShellExecuteInfo)]
            shell.ShellExecuteExW.restype = W.BOOL
            info = ShellExecuteInfo(size=C.sizeof(ShellExecuteInfo), mask=0x40 | 0x100,
                verb='runas', file=str(executable), parameters=subprocess.list2cmdline(arguments),
                directory=os.getcwd(), show=0)
            if not shell.ShellExecuteExW(C.byref(info)):
                raise C.WinError(C.get_last_error())
            self.process = info.process
            handles = (W.HANDLE * 2)(self.ready, self.process)
            if self.kernel.WaitForMultipleObjects(2, handles, False, 25000) != 0:
                raise DisplayLeaseError('Virtual adapter setup failed or timed out')
            if self.kernel.WaitForSingleObject(self.failed, 0) == 0:
                raise DisplayLeaseError('Virtual adapter setup failed')
        except Exception:
            # Caller retains this object and releases the lease before cancel,
            # allowing the helper to acquire it and complete rollback.
            raise

    def cancel(self):
        if self.stop:
            self.kernel.SetEvent(self.stop)
        if self.process:
            state = self.kernel.WaitForMultipleObjects(2, (W.HANDLE * 2)(self.process, self.deferred), False, 25000)
            if state not in (0, 1):
                raise DisplayLeaseError('Virtual adapter cleanup did not finish')
            if state == 0:
                code = W.DWORD()
                if not self.kernel.GetExitCodeProcess(self.process, C.byref(code)) or code.value != 0:
                    raise DisplayLeaseError('Virtual adapter cleanup failed')
            # Deferred cleanup remains in the independent helper until the next
            # owner releases the mutex, including if its UAC request is canceled.
        for handle in (self.ready, self.stop, self.process, self.failed, self.deferred):
            if handle:
                self.kernel.CloseHandle(handle)
        self.ready = self.stop = self.process = self.failed = self.deferred = None


def run_device_guard(payload):
    data = json.loads(base64.urlsafe_b64decode(payload))
    nonce = str(data['nonce'])
    if len(nonce) != 32 or any(c not in '0123456789abcdef' for c in nonce):
        return 1
    kernel = device_kernel()
    parent = kernel.OpenProcess(0x100000 | 0x1000, False, int(data['pid']))
    ready = kernel.OpenEventW(2, False, f'Local\\HDRScreenShare.Ready.{nonce}')
    stop = kernel.OpenEventW(0x100000, False, f'Local\\HDRScreenShare.Stop.{nonce}')
    failed = kernel.OpenEventW(2, False, f'Local\\HDRScreenShare.Failed.{nonce}')
    deferred = kernel.OpenEventW(2, False, f'Local\\HDRScreenShare.Deferred.{nonce}')
    enabled = False
    locked = False
    backend = WindowsDisplayBackend()
    try:
        if not parent or not ready or not stop or not failed or not deferred or creation_time(kernel, parent) != int(data['birth']):
            return 1
        if kernel.WaitForSingleObject(parent, 0) != 258:
            return 1
        enabled = True  # Also roll back a partially successful enable operation.
        try:
            control_owned_device(True)
        except (OSError, subprocess.SubprocessError, DisplayLeaseError):
            logging.exception('Virtual adapter enable failed')
            kernel.SetEvent(failed)
        kernel.SetEvent(ready)
        state = kernel.WaitForMultipleObjects(2, (W.HANDLE * 2)(parent, stop), False, 0xFFFFFFFF)
        if state in (0, 1):  # Parent releases its lease before Stop; death abandons it.
            claim_cleanup_lease(backend, kernel, deferred)
            locked = True
        else:
            return 1
        return 0
    finally:
        try:
            if enabled:
                remove_owned_device()
        finally:
            if locked:
                backend.unclaim()
            for handle in (parent, ready, stop, failed, deferred):
                if handle:
                    kernel.CloseHandle(handle)


def idle_state():
    return DisplayState(False, 0, 0, 0, 0, 60, 32, 0)


def recover_output(backend, identity, expected):
    try:
        backend.claim()
    except DisplayLeaseError:
        return False  # Another live instance owns the display now.
    try:
        if backend.owned_display() != identity:
            return False
        backend.restore(identity, idle_state())
        return True
    finally:
        backend.unclaim()


def kernel_api():
    kernel = C.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    kernel.OpenProcess.restype = W.HANDLE
    kernel.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
    kernel.WaitForSingleObject.restype = W.DWORD
    kernel.GetProcessTimes.argtypes = [W.HANDLE, C.POINTER(W.FILETIME), C.POINTER(W.FILETIME),
                                      C.POINTER(W.FILETIME), C.POINTER(W.FILETIME)]
    kernel.CloseHandle.argtypes = [W.HANDLE]
    return kernel


def creation_time(kernel, handle):
    created, ended, system, user = (W.FILETIME() for _ in range(4))
    if not kernel.GetProcessTimes(handle, C.byref(created), C.byref(ended), C.byref(system), C.byref(user)):
        raise C.WinError(C.get_last_error())
    return (created.dwHighDateTime << 32) | created.dwLowDateTime


class DisplayGuard:
    def __init__(self, identity, expected):
        kernel = kernel_api()
        handle = kernel.OpenProcess(0x1000, False, os.getpid())
        if not handle:
            raise C.WinError(C.get_last_error())
        try:
            birth = creation_time(kernel, handle)
        finally:
            kernel.CloseHandle(handle)
        payload = json.dumps({'pid': os.getpid(), 'birth': birth, 'identity': identity,
                              'expected': asdict(expected)}, separators=(',', ':'))
        command = ([sys.executable] if getattr(sys, 'frozen', False)
                   else [sys.executable, '-m', 'hdr_share'])
        self.process = subprocess.Popen(command + ['--display-guard', payload],
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)

    def cancel(self):
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


def run_guard(payload):
    data = json.loads(payload)
    expected = DisplayState(**data['expected'])
    kernel = kernel_api()
    handle = kernel.OpenProcess(0x100000 | 0x1000, False, int(data['pid']))
    if handle:
        try:
            if creation_time(kernel, handle) == int(data['birth']):
                while True:
                    state = kernel.WaitForSingleObject(handle, 500)
                    if state == 0:
                        break
                    if state != 258:
                        return 1
        finally:
            kernel.CloseHandle(handle)
    elif C.get_last_error() != 87:  # A missing PID is dead; access denied is unknown.
        return 1
    for attempt in range(20):
        try:
            recover_output(WindowsDisplayBackend(), data['identity'], expected)
            return 0
        except Exception:
            time.sleep(.25)
    return 1
