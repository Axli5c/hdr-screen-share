import threading
import time

import numpy as np

from hdr_share.capture import CaptureWorker
from hdr_share.frames import LatestFrame
from hdr_share.monitors import CaptureSource

SOURCE = CaptureSource("display-b", "HDR", True, True, 3840, 2160, 1)


class FakeSession:
    is_hdr = True

    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def grab(self):
        self.calls.append(("read", threading.get_ident()))
        if self.fail:
            raise RuntimeError("device disconnected")
        return type("Frame", (), {"timestamp": 1, "format": "bgra8",
                                    "ndarray": lambda _: np.zeros((2, 2, 4), np.uint8)})()

    def close(self):
        self.calls.append(("close", threading.get_ident()))


def worker_for(session):
    def factory(index, mode):
        assert index == 7  # re-enumerated index, not stale index=1 or Qt order
        assert mode == "auto"
        session.calls.append(("create", threading.get_ident()))
        return session
    current = CaptureSource(SOURCE.id, SOURCE.label, True, True, 3840, 2160, 7)
    return CaptureWorker(SOURCE.id, LatestFrame(), sources=lambda: [current], factory=factory)


def test_resources_live_in_same_worker_and_duplicates_not_counted():
    session = FakeSession()
    worker = worker_for(session)
    worker.start()
    deadline = time.monotonic() + 2
    while worker.captured == 0 and time.monotonic() < deadline:
        time.sleep(.005)
    worker.request_stop()
    assert worker.wait(2500)
    assert worker.captured == 1
    assert session.calls[0][0] == "create"
    assert session.calls[-1][0] == "close"
    assert len({thread for _, thread in session.calls}) == 1
    assert session.calls[0][1] != threading.get_ident()


def test_failure_closes_session_and_retains_actionable_error():
    session = FakeSession(fail=True)
    worker = worker_for(session)
    worker.start()
    assert worker.wait(2500)
    assert "device disconnected" in worker.last_error
    assert session.calls[-1][0] == "close"


def test_disconnected_source_does_not_start_wrong_monitor():
    worker = CaptureWorker(SOURCE.id, LatestFrame(), sources=lambda: [])
    worker.start()
    assert worker.wait(2500)
    assert "display" in worker.last_error.lower()


def test_unmapped_preview_clips_hdr_highlights_without_tone_mapping():
    from hdr_share.capture import unmapped_preview
    raw = np.array([[[2, .5, -.1, 1], [np.nan, np.inf, 0, 1]]], dtype=np.float16)
    pixels = unmapped_preview(raw)
    assert pixels.dtype == np.uint8
    assert tuple(pixels[0, 0]) == (0, 188, 255, 255)
    assert tuple(pixels[0, 1]) == (0, 255, 0, 255)


def test_comparison_is_optional_and_closes_raw_session_while_stream_continues():
    from hdr_share.frames import FrameMailbox
    modes, closed = [], []
    class Session:
        is_hdr = True
        def __init__(self, mode): self.mode = mode
        def grab(self):
            mode = self.mode
            return type('Frame', (), {'timestamp': time.monotonic(),
                'format': 'rgba16f' if mode == 'hdr' else 'bgra8',
                'ndarray': lambda _: np.ones((4, 8, 4), np.float16 if mode == 'hdr' else np.uint8)})()
        def close(self): closed.append(self.mode)
    def factory(index, mode):
        modes.append(mode)
        return Session(mode)
    worker = CaptureWorker(SOURCE.id, FrameMailbox(), sources=lambda: [SOURCE], factory=factory)
    def wait_for(condition):
        deadline = time.monotonic() + 2
        while not condition() and time.monotonic() < deadline: time.sleep(.005)
        assert condition()
    worker.start()
    try:
        wait_for(lambda: worker.captured > 1)
        assert modes == ['auto']
        worker.set_comparison_enabled(True)
        wait_for(lambda: worker.comparison_frames.latest_after(0) is not None)
        assert modes == ['auto', 'hdr']
        assert worker.comparison_frames.latest_after(0)[1].shape == (4, 8, 4)
        worker.set_comparison_enabled(False)
        count = worker.captured
        wait_for(lambda: 'hdr' in closed and worker.captured > count)
        assert worker.comparison_frames.latest_after(0) is None
    finally:
        worker.request_stop()
        assert worker.wait(2500)
    assert closed == ['hdr', 'auto']


def test_comparison_failure_does_not_stop_processed_video():
    from hdr_share.frames import FrameMailbox
    def factory(index, mode):
        if mode == 'hdr': raise RuntimeError('raw capture unavailable')
        return FakeSession()
    worker = CaptureWorker(SOURCE.id, FrameMailbox(), sources=lambda: [SOURCE], factory=factory)
    worker.set_comparison_enabled(True)
    worker.start()
    try:
        deadline = time.monotonic() + 2
        while 'unavailable' not in worker.comparison_status and time.monotonic() < deadline:
            time.sleep(.005)
        assert 'raw capture unavailable' in worker.comparison_status
        assert worker.isRunning() and worker.captured > 0 and not worker.last_error
    finally:
        worker.request_stop()
        assert worker.wait(2500)
