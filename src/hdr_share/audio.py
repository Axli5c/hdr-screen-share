"""WASAPI bridge lifecycle. PCM stays in the native module."""
import ctypes as C
import os
from pathlib import Path
import sys
import threading

from .audio_policy import AudioPolicyError, ProcessIdentity, select_capture_roots


class AudioError(RuntimeError):
    pass


class ProcessInfo(C.Structure):
    _fields_ = [('pid', C.c_uint32), ('parent_pid', C.c_uint32),
                ('created_at', C.c_uint64), ('image_name', C.c_wchar * 260)]


class Stats(C.Structure):
    _fields_ = [('output_frames', C.c_uint64), ('queued_frames', C.c_uint32),
                ('overflows', C.c_uint64), ('last_hresult', C.c_int32)]


class EndpointInfo(C.Structure):
    _fields_ = [('id', C.c_wchar * 512), ('name', C.c_wchar * 256), ('default_roles', C.c_uint32)]


def _check(code):
    if code < 0:
        raise AudioError(f'WASAPI: HRESULT 0x{code & 0xffffffff:08X}')


class NativeAudioBridge:
    def __init__(self, path=None):
        self.system_sounds_unavailable = False
        if path is None:
            path = (Path(sys._MEIPASS) / 'audio_bridge.dll' if getattr(sys, 'frozen', False)
                    else Path(__file__).resolve().parents[2] / 'build/native/audio_bridge.dll')
        try:
            self.lib = C.CDLL(str(path))
        except OSError as error:
            raise AudioError(f'Cannot load audio_bridge.dll: {error}') from error
        signatures = {
            'ab_open': [C.c_wchar_p, C.POINTER(C.c_void_p)],
            'ab_stop': [C.c_void_p],
            'ab_set_sources': [C.c_void_p, C.POINTER(ProcessInfo), C.c_uint32],
            'ab_get_stats': [C.c_void_p, C.POINTER(Stats)],
            'ab_list_processes': [C.POINTER(ProcessInfo), C.c_uint32, C.POINTER(C.c_uint32)],
            'ab_list_audio_pids': [C.POINTER(C.c_uint32), C.c_uint32, C.POINTER(C.c_uint32)],
            'ab_list_endpoints': [C.POINTER(EndpointInfo), C.c_uint32, C.POINTER(C.c_uint32)],
        }
        try:
            for name, arguments in signatures.items():
                function = getattr(self.lib, name)
                function.argtypes = arguments
                function.restype = C.c_int32
        except AttributeError as error:
            raise AudioError('Incompatible audio_bridge.dll') from error

    def _list(self, name, record):
        function = getattr(self.lib, name)
        count = C.c_uint32()
        code = function(None, 0, C.byref(count))
        if code != -2147024774:  # ERROR_INSUFFICIENT_BUFFER; empty is S_OK.
            _check(code)
        for _ in range(4):
            capacity = count.value
            if capacity > 65536:
                raise AudioError('Unexpected native list size')
            buffer = (record * capacity)()
            code = function(buffer, capacity, C.byref(count))
            if code == -2147024774:
                continue
            _check(code)
            if name == 'ab_list_audio_pids':
                self.system_sounds_unavailable = code == 1
            return list(buffer[:count.value])
        raise AudioError('Audio devices are changing. Restart capture.')

    def endpoints(self):
        return [{'id': item.id, 'name': item.name, 'default_roles': item.default_roles}
                for item in self._list('ab_list_endpoints', EndpointInfo)]

    def processes(self):
        return [ProcessIdentity(item.pid, item.parent_pid, item.created_at, item.image_name)
                for item in self._list('ab_list_processes', ProcessInfo)]

    def audio_pids(self):
        return set(self._list('ab_list_audio_pids', C.c_uint32))

    def open(self, endpoint_id):
        handle = C.c_void_p()
        _check(self.lib.ab_open(endpoint_id, C.byref(handle)))
        if not handle.value:
            raise AudioError('WASAPI returned an empty relay handle')
        return handle

    def close(self, handle):
        _check(self.lib.ab_stop(handle))

    def set_sources(self, handle, roots):
        records = (ProcessInfo * len(roots))()
        for record, process in zip(records, roots):
            record.pid, record.parent_pid = process.pid, process.parent_pid
            record.created_at, record.image_name = process.created_at, process.image_name
        _check(self.lib.ab_set_sources(handle, records, len(roots)))

    def stats(self, handle):
        result = Stats()
        _check(self.lib.ab_get_stats(handle, C.byref(result)))
        return {name: getattr(result, name) for name, _ in Stats._fields_}


class AudioRelay:
    def __init__(self, endpoint_id, *, bridge=None, refresh_interval=0.2):
        self.endpoint_id = endpoint_id
        self.bridge = bridge if bridge is not None else NativeAudioBridge()
        self.refresh_interval = refresh_interval
        self.last_error = ''
        self.warning = ''
        self._handle = None
        self._roots = None
        self._thread = None
        self._stop = threading.Event()
        self._lock = threading.RLock()

    def start(self):
        with self._lock:
            if self._handle is not None:
                return
            self._stop.clear()
            self.last_error = ''
            self._handle = self.bridge.open(self.endpoint_id)
            try:
                self.refresh()
            except Exception:
                self._close()
                raise
            self._thread = threading.Thread(target=self._run, daemon=True, name='audio-policy')
            self._thread.start()

    def refresh(self):
        with self._lock:
            if self._handle is None:
                return
            try:
                active = self.bridge.audio_pids()
                self.warning = ('Windows system sounds unavailable' if
                    getattr(self.bridge, 'system_sounds_unavailable', False) else '')
                processes = self.bridge.processes()
                roots = select_capture_roots(processes, active, os.getpid())
                if roots != self._roots:
                    self.bridge.set_sources(self._handle, roots)
                    self._roots = roots
                stats = self.bridge.stats(self._handle)
                _check(stats['last_hresult'])
            except (AudioError, AudioPolicyError) as error:
                self.last_error = str(error)
                try:
                    self.bridge.set_sources(self._handle, [])
                finally:
                    self._close()
                raise AudioError(str(error)) from error

    def _run(self):
        while not self._stop.wait(self.refresh_interval):
            try:
                self.refresh()
            except Exception as error:
                self.last_error = str(error)
                with self._lock:
                    self._close()
                return

    def stats(self):
        with self._lock:
            return self.bridge.stats(self._handle) if self._handle is not None else {'last_error': self.last_error}

    def _close(self):
        handle, self._handle = self._handle, None
        self._roots = None
        if handle is not None:
            self.bridge.close(handle)

    def stop(self):
        self._stop.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join()
        self._thread = None
        with self._lock:
            self._close()
