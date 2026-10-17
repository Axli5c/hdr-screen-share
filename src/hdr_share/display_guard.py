"""Small parent-process watchdog; never starts capture or audio."""
import ctypes as C
from ctypes import wintypes as W
from dataclasses import asdict
import json
import os
import subprocess
import sys
import time

from .virtual_display import DisplayLeaseError, DisplayState, WindowsDisplayBackend


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
