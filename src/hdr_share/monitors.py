"""Read-only Windows display discovery in the same order as hdrcapture."""
import ctypes as C
from ctypes import wintypes as W
from dataclasses import dataclass


@dataclass(frozen=True)
class CaptureSource:
    id: str
    label: str
    primary: bool
    hdr_enabled: bool | None
    width: int
    height: int
    index: int
    left: int = 0
    top: int = 0


def default_source(sources: list[CaptureSource]) -> CaptureSource:
    if not sources:
        raise RuntimeError("Windows не обнаружила подключённых мониторов")
    return min(sources, key=lambda s: (
        not (s.primary and s.hdr_enabled is True),
        s.hdr_enabled is not True, not s.primary,
    ))


def hdr_from_info(active_mode: int | None, legacy_flags: int | None) -> bool | None:
    if active_mode is not None:
        return active_mode == 2  # DISPLAYCONFIG_ADVANCED_COLOR_MODE_HDR
    if legacy_flags is not None:
        return bool(legacy_flags & 2)
    return None


class Luid(C.Structure):
    _fields_ = [("low", W.DWORD), ("high", W.LONG)]


class Rational(C.Structure):
    _fields_ = [("numerator", W.UINT), ("denominator", W.UINT)]


class PathSource(C.Structure):
    _fields_ = [("adapter", Luid), ("id", W.UINT), ("mode", W.UINT), ("flags", W.UINT)]


class PathTarget(C.Structure):
    _fields_ = [("adapter", Luid), ("id", W.UINT), ("mode", W.UINT),
                ("technology", W.UINT), ("rotation", W.UINT), ("scaling", W.UINT),
                ("refresh", Rational), ("scanline", W.UINT), ("available", W.BOOL),
                ("flags", W.UINT)]


class DisplayPath(C.Structure):
    _fields_ = [("source", PathSource), ("target", PathTarget), ("flags", W.UINT)]


class Mode(C.Structure):
    _fields_ = [("type", W.UINT), ("id", W.UINT), ("adapter", Luid), ("data", C.c_uint64 * 6)]


class Header(C.Structure):
    _fields_ = [("type", W.UINT), ("size", W.UINT), ("adapter", Luid), ("id", W.UINT)]


class SourceName(C.Structure):
    _fields_ = [("header", Header), ("name", W.WCHAR * 32)]


class ColorInfo(C.Structure):
    _fields_ = [("header", Header), ("value", W.UINT), ("encoding", W.UINT), ("bits", W.UINT)]


class ColorInfo2(C.Structure):
    _fields_ = ColorInfo._fields_ + [("active_mode", W.UINT)]


class MonitorInfo(C.Structure):
    _fields_ = [("size", W.DWORD), ("monitor", W.RECT), ("work", W.RECT),
                ("flags", W.DWORD), ("device", W.WCHAR * 32)]


def _hdr_states(user32) -> dict[str, bool | None]:
    result = {}
    for _ in range(3):  # Display topology can change between sizing and querying.
        paths_count, modes_count = W.UINT(), W.UINT()
        if user32.GetDisplayConfigBufferSizes(2, C.byref(paths_count), C.byref(modes_count)):
            return result
        paths, modes = (DisplayPath * paths_count.value)(), (Mode * modes_count.value)()
        status = user32.QueryDisplayConfig(2, C.byref(paths_count), paths,
                                         C.byref(modes_count), modes, None)
        if status == 122:
            continue
        if status:
            return result
        for path in paths[:paths_count.value]:
            name = SourceName()
            name.header = Header(1, C.sizeof(name), path.source.adapter, path.source.id)
            if user32.DisplayConfigGetDeviceInfo(C.byref(name)):
                continue
            modern = ColorInfo2()
            modern.header = Header(15, C.sizeof(modern), path.target.adapter, path.target.id)
            if user32.DisplayConfigGetDeviceInfo(C.byref(modern)) == 0:
                state = hdr_from_info(modern.active_mode, None)
            else:
                legacy = ColorInfo()
                legacy.header = Header(9, C.sizeof(legacy), path.target.adapter, path.target.id)
                status = user32.DisplayConfigGetDeviceInfo(C.byref(legacy))
                state = hdr_from_info(None, legacy.value if status == 0 else None)
            # Clone paths can share a GDI source: do not assert HDR if targets disagree.
            if name.name in result and result[name.name] != state:
                result[name.name] = None
            else:
                result[name.name] = state
        break
    return result


def list_sources() -> list[CaptureSource]:
    user32 = C.WinDLL("user32", use_last_error=True)
    user32.GetMonitorInfoW.argtypes = [W.HANDLE, C.POINTER(MonitorInfo)]
    user32.GetMonitorInfoW.restype = W.BOOL
    states = _hdr_states(user32)
    sources = []
    callback_error = []
    callback_type = C.WINFUNCTYPE(W.BOOL, W.HANDLE, W.HDC, C.POINTER(W.RECT), W.LPARAM)

    @callback_type
    def visit(handle, hdc, rect, data):
        info = MonitorInfo()
        info.size = C.sizeof(info)
        if not user32.GetMonitorInfoW(handle, C.byref(info)):
            callback_error.append(C.get_last_error())
            return False
        r = info.monitor
        sources.append(CaptureSource(info.device, info.device, bool(info.flags & 1),
                                     states.get(info.device), r.right - r.left,
                                     r.bottom - r.top, len(sources), r.left, r.top))
        return True

    user32.EnumDisplayMonitors.argtypes = [W.HDC, C.POINTER(W.RECT), callback_type, W.LPARAM]
    user32.EnumDisplayMonitors.restype = W.BOOL
    if not user32.EnumDisplayMonitors(None, None, visit, 0) or callback_error:
        raise RuntimeError("Не удалось получить список мониторов Windows")
    return sources


def enable_physical_pixels() -> None:
    C.windll.user32.SetProcessDpiAwarenessContext(C.c_void_p(-4))
