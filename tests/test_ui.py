import gc
import time

import numpy as np
from PySide6.QtCore import QRect

from hdr_share.ui import OutputWindow, ControlWindow, output_dimensions, choose_output, match_screen
from hdr_share.monitors import CaptureSource
from hdr_share.capture import CaptureWorker


def control_for_test(app, sources, factory, autostart=True, affinity=lambda hwnd: True):
    from hdr_share.stream import StreamController
    target_id = sources[0].id if sources[0].id == 'sdr' else 'b'
    class Lease:
        def acquire(self): return next(s for s in sources if s.id == target_id)
        def release(self): pass
    def no_audio(): raise RuntimeError('test audio disabled')
    controller = StreamController(sources=lambda: sources, worker_factory=factory,
        lease_factory=lambda *args: Lease(), audio_factory=no_audio,
        screen_lookup=lambda _: app.primaryScreen())
    return ControlWindow(sources=lambda: sources, controller=controller,
        screen_lookup=lambda _: app.primaryScreen(), autostart=autostart,
        owned_display=lambda: target_id, affinity=affinity)


def test_preview_does_not_reduce_stream_resolution(app):
    from hdr_share.ui import PreviewWidget
    pixels = np.zeros((2160, 3840, 4), np.uint8)
    preview, stream = PreviewWidget(), OutputWindow()
    preview.set_frame(pixels)
    stream.set_frame(pixels)
    assert preview.image.width() <= 480 and preview.image.height() <= 270
    assert stream.output_size == (3840, 2160)
    preview.close(); stream.close()


def test_modes_have_short_english_instructions(app):
    sources = [CaptureSource('a', 'HDR', True, True, 3840, 2160, 0),
               CaptureSource('b', 'own', False, False, 3840, 2160, 1, 3840, 0)]
    window = control_for_test(app, sources, None, autostart=False)
    assert window.share_mode.currentText() == 'Virtual screen'
    assert 'system audio' in window.instruction.text().lower()
    window.share_mode.setCurrentIndex(1)
    assert window.share_mode.currentText() == 'Application window'
    assert 'HDR Screen Share' in window.instruction.text()
    assert window.start_button.text() == 'Start'
    assert window.output.windowTitle() == 'HDR Screen Share'
    window.close()


def test_preview_owns_small_image_when_no_scaling_is_needed(app):
    from hdr_share.ui import PreviewWidget
    pixels = np.full((270, 480, 4), 20, np.uint8)
    preview = PreviewWidget()
    preview.set_frame(pixels)
    pixels[:] = 99
    assert preview.image.pixelColor(0, 0).red() == 20
    preview.close()


def test_control_exclusion_does_not_exclude_stream_hwnd(app):
    sources = [CaptureSource('a', 'HDR', True, True, 3840, 2160, 0),
               CaptureSource('b', 'own', False, False, 3840, 2160, 1, 3840, 0)]
    calls = []
    window = control_for_test(app, sources, None, autostart=False,
                              affinity=lambda hwnd: calls.append(hwnd) or True)
    window.show()
    app.processEvents()
    assert calls == [int(window.winId())]
    assert int(window.output.winId()) not in calls
    assert window.monitors.count() == 1
    assert window.monitors.currentData() == 'a'
    window.close()


def test_minimize_pauses_preview_not_stream(app):
    sources = [CaptureSource('a', 'HDR', True, True, 3840, 2160, 0),
               CaptureSource('b', 'own', False, False, 3840, 2160, 1, 3840, 0)]
    window = control_for_test(app, sources, None, autostart=False)
    window.controller.running = True
    window.controller.frames.publish(np.zeros((8, 16, 4), np.uint8), 0)
    window.showMinimized()
    window.present_preview()
    window.present_latest()
    assert window.preview.received == 0
    assert window.output.received == 1
    window.close()


def pump(app, condition, seconds=2):
    deadline = time.monotonic() + seconds
    while not condition() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.005)
    assert condition()


def test_output_owns_pixels_and_uses_4k_physical_size(app):
    window = OutputWindow()
    pixels = np.zeros((2160, 3840, 4), np.uint8)
    pixels[:] = (12, 34, 56, 255)
    window.set_frame(pixels)
    del pixels
    gc.collect()
    assert window.image.pixelColor(0, 0).getRgb() == (56, 34, 12, 255)
    assert window.output_size == (3840, 2160)
    window.close()


def test_output_fits_target_in_physical_pixels_without_upscaling():
    assert output_dimensions(3840, 2160, 3840, 2160) == (3840, 2160)
    assert output_dimensions(3840, 2160, 2560, 1440) == (2560, 1440)
    assert output_dimensions(1280, 720, 3840, 2160) == (1280, 720)


def test_output_never_uses_captured_monitor():
    assert choose_output(["a", "b", "c"], "a", "c") == "c"
    assert choose_output(["a", "b"], "a", "a") == "b"
    assert choose_output(["a"], "a", None) is None


def test_matches_friendly_qt_names_to_windows_by_physical_geometry():
    class Screen:
        def __init__(self, x, width, ratio):
            self.x, self.width, self.ratio = x, width, ratio

        def geometry(self):
            return QRect(self.x, 0, self.width, 1440)

        def devicePixelRatio(self):
            return self.ratio
    primary = Screen(0, 2560, 1.5)
    secondary = Screen(-2560, 2560, 1)
    source = CaptureSource("DISPLAY2", "HDR", True, True, 3840, 2160, 1, 0, 0)
    assert match_screen(source, [secondary, primary]) is primary


def test_start_error_retry_and_shutdown(app):
    sources = [CaptureSource("sdr", "SDR", True, False, 2560, 1440, 0),
               CaptureSource("hdr", "HDR", False, True, 3840, 2160, 1)]
    created = []

    class Session:
        is_hdr = True

        def grab(self):
            if len(created) == 1:
                raise RuntimeError("GPU unavailable")
            return type("Frame", (), {"timestamp": time.monotonic(), "format": "bgra8",
                        "ndarray": lambda _: np.zeros((10, 20, 4), np.uint8)})()

        def close(self):
            pass

    def factory(source_id, slot):
        created.append(source_id)
        return CaptureWorker(source_id, slot, sources=lambda: sources,
                             factory=lambda index, mode: Session())

    window = control_for_test(app, sources, factory)
    pump(app, lambda: "GPU unavailable" in window.status.text())
    assert created == ["hdr"]
    window.start_capture()
    pump(app, lambda: window.worker is not None and window.worker.captured > 0)
    worker = window.worker
    assert window.stop_capture()
    assert not worker.isRunning()
    window.close()


def test_target_removal_or_reposition_stops_output_safely(app):
    sources = [CaptureSource("a", "HDR", True, True, 3840, 2160, 0),
               CaptureSource("b", "SDR", False, False, 3840, 2160, 1, -3840, 0)]

    class Session:
        is_hdr = True

        def grab(self):
            return type("Frame", (), {"timestamp": time.monotonic(), "format": "bgra8",
                        "ndarray": lambda _: np.zeros((10, 20, 4), np.uint8)})()

        def close(self):
            pass

    def factory(source_id, slot):
        return CaptureWorker(source_id, slot, sources=lambda: sources,
                             factory=lambda index, mode: Session())

    window = control_for_test(app, sources, factory, autostart=False)
    for remove in (False, True):
        window.start_capture()
        pump(app, lambda: window.worker is not None and window.worker.captured > 0)
        running = window.worker
        if remove:
            sources.pop()
        else:
            sources[1] = CaptureSource("b", "SDR", False, False, 3840, 2160, 1, -4000, 0)
        window.verify_displays()
        assert not running.isRunning()
        assert not window.timer.isActive()
        assert window.output.isHidden()
        assert "display" in window.status.text().lower()
    window.close()
