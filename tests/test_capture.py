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
