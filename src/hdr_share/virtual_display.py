"""Lease a dedicated output; never restore a whole-desktop snapshot."""
from typing import Protocol
import ctypes as C
from ctypes import wintypes as W
from dataclasses import dataclass
import winreg
import threading

from .monitors import CaptureSource, list_sources, Header, DisplayPath, Mode, SourceName


class DisplayLeaseError(RuntimeError):
    pass


class DisplayBackend(Protocol):
    def claim(self) -> None: ...
    def unclaim(self) -> None: ...
    def owned_display(self) -> str | None: ...
    def snapshot(self, identity: str): ...
    def attach(self, identity: str, width: int, height: int) -> CaptureSource: ...
    def restore(self, identity: str, snapshot) -> None: ...


class DisplayLease:
    def __init__(self, source_id: str, width: int, height: int, *, backend=None):
        if width < 1 or height < 1 or max(width, height) > 3840 or min(width, height) > 2160:
            raise ValueError('Unsupported output size')
        self.source_id, self.width, self.height = source_id, width, height
        self.backend = backend if backend is not None else WindowsDisplayBackend()
        self._identity = self._before = self._applied = self._source = None
        self._claimed = False

    def acquire(self) -> CaptureSource:
        if self._source is not None:
            return self._source
        self.backend.claim()
        self._claimed = True
        try:
            identity = self.backend.owned_display()
            if identity is None:
                raise DisplayLeaseError('No app-owned virtual display is registered')
            if identity == self.source_id:
                raise DisplayLeaseError('Output cannot be captured as input')
            before = self.backend.snapshot(identity)
            source = self.backend.attach(identity, self.width, self.height)
            self._identity, self._before = identity, before
            self._applied = self.backend.snapshot(identity)
            self._source = source
            return source
        except Exception:
            self.backend.unclaim()
            self._claimed = False
            raise

    def release(self) -> None:
        if self._identity is None:
            return
        identity, before, applied = self._identity, self._before, self._applied
        self._identity = self._before = self._applied = self._source = None
        try:
            if self.backend.owned_display() == identity and self.backend.snapshot(identity) == applied:
                self.backend.restore(identity, before)
        finally:
            if self._claimed:
                self.backend.unclaim()
                self._claimed = False


OWN_INSTANCE = r'ROOT\HDRSCREENSHAREVDD\0000'
PACKAGE_HASH = 'F93E7CE3D640C83C419B1B72D2C83B2D8E34D83E8B7BA11F3328A40D2DA82FA4'


def is_owned_adapter_path(path: str) -> bool:
    prefix = '\\\\?\\'
    return path.startswith(prefix) and '\\'.join(path[len(prefix):].split('#')[:3]).upper() == OWN_INSTANCE


class AdapterName(C.Structure):
    _fields_ = [('header', Header), ('name', W.WCHAR * 128)]


class DisplayDevice(C.Structure):
    _fields_ = [('size', W.DWORD), ('name', W.WCHAR * 32),
                ('label', W.WCHAR * 128), ('flags', W.DWORD),
                ('identity', W.WCHAR * 128), ('key', W.WCHAR * 128)]


class DevMode(C.Structure):
    _fields_ = [('device', W.WCHAR * 32), ('spec', W.WORD), ('driver', W.WORD),
                ('size', W.WORD), ('extra', W.WORD), ('fields', W.DWORD),
                ('x', W.LONG), ('y', W.LONG), ('orientation', W.DWORD),
                ('fixed', W.DWORD), ('color', W.SHORT), ('duplex', W.SHORT),
                ('y_resolution', W.SHORT), ('tt_option', W.SHORT), ('collate', W.SHORT),
                ('form', W.WCHAR * 32), ('log_pixels', W.WORD),
                ('bits', W.DWORD), ('width', W.DWORD), ('height', W.DWORD),
                ('display_flags', W.DWORD), ('frequency', W.DWORD),
                ('icm_method', W.DWORD), ('icm_intent', W.DWORD), ('media', W.DWORD),
                ('dither', W.DWORD), ('reserved1', W.DWORD), ('reserved2', W.DWORD),
                ('pan_width', W.DWORD), ('pan_height', W.DWORD)]


@dataclass(frozen=True)
class DisplayState:
    active: bool
    x: int
    y: int
    width: int
    height: int
    frequency: int
    bits: int
    orientation: int


class WindowsDisplayBackend:
    _claim_guard = threading.Lock()
    _claimed_in_process = False
    def __init__(self):
        self._mutex = None
        self.kernel32 = C.WinDLL('kernel32', use_last_error=True)
        self.kernel32.CreateMutexW.argtypes = [W.LPVOID, W.BOOL, W.LPCWSTR]
        self.kernel32.CreateMutexW.restype = W.HANDLE
        self.kernel32.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
        self.kernel32.WaitForSingleObject.restype = W.DWORD
        self.kernel32.ReleaseMutex.argtypes = [W.HANDLE]
        self.kernel32.CloseHandle.argtypes = [W.HANDLE]
        self.user32 = C.WinDLL('user32', use_last_error=True)
        self.user32.EnumDisplayDevicesW.argtypes = [W.LPCWSTR, W.DWORD, C.POINTER(DisplayDevice), W.DWORD]
        self.user32.EnumDisplayDevicesW.restype = W.BOOL
        self.user32.EnumDisplaySettingsExW.argtypes = [W.LPCWSTR, W.DWORD, C.POINTER(DevMode), W.DWORD]
        self.user32.EnumDisplaySettingsExW.restype = W.BOOL
        self.user32.ChangeDisplaySettingsExW.argtypes = [W.LPCWSTR, C.POINTER(DevMode), W.HWND, W.DWORD, W.LPVOID]
        self.user32.ChangeDisplaySettingsExW.restype = W.LONG

    def claim(self):
        with self._claim_guard:
            if self._mutex is not None or WindowsDisplayBackend._claimed_in_process:
                raise DisplayLeaseError('Display already owned by this process')
            handle = self.kernel32.CreateMutexW(None, False, 'Local\\HDRScreenShare.VirtualDisplayLease')
            if not handle:
                raise DisplayLeaseError('Cannot create owned display lock')
            if self.kernel32.WaitForSingleObject(handle, 0) not in (0, 0x80):
                self.kernel32.CloseHandle(handle)
                raise DisplayLeaseError('Virtual display already owned by another application instance')
            self._mutex = handle
            WindowsDisplayBackend._claimed_in_process = True

    def unclaim(self):
        with self._claim_guard:
            if self._mutex is not None:
                self.kernel32.ReleaseMutex(self._mutex)
                self.kernel32.CloseHandle(self._mutex)
                self._mutex = None
                WindowsDisplayBackend._claimed_in_process = False

    def _devices(self):
        index = 0
        while True:
            device = DisplayDevice(size=C.sizeof(DisplayDevice))
            if not self.user32.EnumDisplayDevicesW(None, index, C.byref(device), 0):
                break
            yield device
            index += 1

    def owned_display(self) -> str | None:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\HDRScreenShare') as key:
                identity = winreg.QueryValueEx(key, 'DeviceInstance')[0]
                digest = winreg.QueryValueEx(key, 'PackageHash')[0]
            if identity.upper() != OWN_INSTANCE or digest.upper() != PACKAGE_HASH:
                return None
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                'SYSTEM\\CurrentControlSet\\Enum\\' + OWN_INSTANCE) as key:
                hardware = winreg.QueryValueEx(key, 'HardwareID')[0]
            if not any(item.casefold() == r'root\mttvdd' for item in hardware):
                return None
        except OSError:
            return None
        # EnumDisplayDevices reports only hardware ID (Root\MttVDD). Resolve the
        # complete PnP instance through DisplayConfig adapter interfaces instead.
        for _ in range(3):
            n, m = W.UINT(), W.UINT()
            if self.user32.GetDisplayConfigBufferSizes(1, C.byref(n), C.byref(m)):
                return None
            paths, modes = (DisplayPath * n.value)(), (Mode * m.value)()
            status = self.user32.QueryDisplayConfig(1, C.byref(n), paths, C.byref(m), modes, None)
            if status == 122:
                continue
            if status:
                return None
            matches = set()
            for path in paths[:n.value]:
                adapter = AdapterName()
                adapter.header = Header(4, C.sizeof(adapter), path.source.adapter, 0)
                if self.user32.DisplayConfigGetDeviceInfo(C.byref(adapter)) or not is_owned_adapter_path(adapter.name):
                    continue
                source = SourceName()
                source.header = Header(1, C.sizeof(source), path.source.adapter, path.source.id)
                if not self.user32.DisplayConfigGetDeviceInfo(C.byref(source)):
                    matches.add(source.name)
            return next(iter(matches)) if len(matches) == 1 else None
        return None

    def _device(self, identity):
        if self.owned_display() != identity:
            raise DisplayLeaseError('Owned display identity changed')
        return next(device for device in self._devices() if device.name == identity)

    def snapshot(self, identity) -> DisplayState:
        device = self._device(identity)
        mode = DevMode(size=C.sizeof(DevMode))
        active = bool(device.flags & 1)
        if not self.user32.EnumDisplaySettingsExW(identity, 0xFFFFFFFF if active else 0xFFFFFFFE,
                                                 C.byref(mode), 0):
            raise DisplayLeaseError('Cannot read owned display mode')
        return DisplayState(active, mode.x, mode.y, mode.width, mode.height,
                            mode.frequency, mode.bits, mode.orientation)

    def _apply(self, identity, state):
        self._device(identity)
        mode = DevMode(size=C.sizeof(DevMode))
        if state.active:
            index = 0
            while self.user32.EnumDisplaySettingsExW(identity, index, C.byref(mode), 0):
                if (mode.width, mode.height, mode.frequency, mode.bits) == (state.width, state.height, state.frequency, state.bits):
                    break
                index += 1
                mode = DevMode(size=C.sizeof(DevMode))
            else:
                raise DisplayLeaseError('Requested output mode is not advertised by the driver')
        mode.fields = 0x20 | 0x80000 | 0x100000  # position, width, height
        mode.x, mode.y = state.x, state.y
        if state.active:
            mode.fields |= 0x40000 | 0x400000 | 0x80  # bits, frequency, orientation
            mode.width, mode.height = state.width, state.height
            mode.bits, mode.frequency, mode.orientation = state.bits, state.frequency, state.orientation
        # Address only this device; never apply a saved global topology.
        # Detached indirect displays require staging before enabling. Commit the
        # same named device, never NULL (which would apply all pending devices).
        status = self.user32.ChangeDisplaySettingsExW(identity, C.byref(mode), None,
                                                     0x10000001 if state.active else 1, None)
        if status == 0 and state.active:
            status = self.user32.ChangeDisplaySettingsExW(identity, None, None, 0, None)
        if status != 0:
            raise DisplayLeaseError(f'Windows rejected owned display mode: {status}')

    def attach(self, identity, width, height):
        physical = [source for source in list_sources() if source.id != identity]
        x = max((source.left + source.width for source in physical), default=0)
        state = DisplayState(True, x, 0, width, height, 60, 32, 0)
        before = self.snapshot(identity)
        self._apply(identity, state)
        try:
            source = next(source for source in list_sources() if source.id == identity)
            if (source.width, source.height) != (width, height) or source.primary or source.hdr_enabled is not False:
                raise DisplayLeaseError('Owned output must be SDR at the requested size')
            return source
        except Exception:
            if self.snapshot(identity) == state:
                self._apply(identity, before)
            raise

    def restore(self, identity, snapshot):
        self._apply(identity, snapshot)

    def detach_initial_output(self):
        """One-time install probe: explicitly detach the known dedicated output."""
        identity = self.owned_display()
        if identity is None:
            raise DisplayLeaseError('No validated owned display')
        self._apply(identity, DisplayState(False, 0, 0, 0, 0, 60, 32, 0))
