"""Present SDR frames to a capturable window without attaching a monitor."""
import ctypes as C
from pathlib import Path
import sys

import numpy as np


class VideoError(RuntimeError):
    pass


def check(code):
    if code < 0:
        raise VideoError(f'Direct3D: HRESULT 0x{code & 0xffffffff:08X}')


class VideoPresenter:
    def __init__(self, hwnd, width, height):
        path = (Path(sys._MEIPASS) / 'video_presenter.dll' if getattr(sys, 'frozen', False)
                else Path(__file__).resolve().parents[2] / 'build/native/video_presenter.dll')
        self.lib = C.CDLL(str(path))
        self.lib.vp_create.argtypes = [C.c_void_p, C.c_uint32, C.c_uint32, C.POINTER(C.c_void_p)]
        self.lib.vp_create.restype = C.c_long
        self.lib.vp_present.argtypes = [C.c_void_p, C.c_void_p, C.c_uint32, C.c_uint32, C.c_uint32]
        self.lib.vp_present.restype = C.c_long
        self.lib.vp_destroy.argtypes = [C.c_void_p]
        self.lib.vp_destroy.restype = None
        self.handle = C.c_void_p()
        self.size = width, height
        check(self.lib.vp_create(hwnd, width, height, C.byref(self.handle)))

    def present(self, pixels):
        if not self.handle or pixels.dtype != np.uint8 or pixels.ndim != 3 or pixels.shape[2] != 4:
            raise VideoError('Expected BGRA8 frame')
        height, width, _ = pixels.shape
        if (width, height) != self.size:
            raise VideoError('Output dimensions changed')
        pixels = np.ascontiguousarray(pixels)
        check(self.lib.vp_present(self.handle, pixels.ctypes.data, width, height, pixels.strides[0]))

    def close(self):
        if self.handle:
            self.lib.vp_destroy(self.handle)
            self.handle = C.c_void_p()
