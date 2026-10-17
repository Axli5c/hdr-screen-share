import time

import numpy as np

from hdr_share.capture import CaptureWorker
from hdr_share.monitors import CaptureSource
from hdr_share.stream import StreamController
from hdr_share.ui import OutputWindow


def setup_controller(app, *, bad_audio=False, bad_display=False):
    sources = [CaptureSource('hdr', 'HDR', True, True, 3840, 2160, 0),
               CaptureSource('own', 'SDR', False, False, 3840, 2160, 1, 3840, 0)]
    events = []
    class Lease:
        def acquire(self):
            if bad_display: raise RuntimeError('display unavailable')
            events.append('acquire')
            return sources[1]
        def release(self): events.append('release')
    class Audio:
        last_error = ''
        def start(self):
            if bad_audio: raise RuntimeError('audio unavailable')
            events.append('audio-start')
        def stop(self): events.append('audio-stop')
    class Session:
        is_hdr = True
        def grab(self):
            time.sleep(.005)
            return type('Frame', (), {'timestamp': time.monotonic(), 'format': 'bgra8',
                'ndarray': lambda _: np.zeros((10, 20, 4), np.uint8)})()
        def close(self): events.append('capture-close')
    def factory(source_id, frames):
        return CaptureWorker(source_id, frames, sources=lambda: sources,
                             factory=lambda index, mode: Session())
    controller = StreamController(sources=lambda: sources, lease_factory=lambda *args: Lease(),
        audio_factory=lambda: Audio(), worker_factory=factory,
        screen_lookup=lambda _: app.primaryScreen(), output_factory=OutputWindow)
    return controller, sources, events


def test_audio_failure_leaves_video_with_visible_error(app):
    controller, _, events = setup_controller(app, bad_audio=True)
    controller.start('hdr')
    assert controller.running
    assert 'audio unavailable' in controller.audio_status
    controller.stop()
    assert events.count('release') == 1


def test_display_failure_is_retryable(app):
    controller, _, _ = setup_controller(app, bad_display=True)
    controller.start('hdr')
    assert not controller.running
    assert controller.output.isHidden()
    assert 'display unavailable' in controller.video_status
    controller.stop()


def test_stop_hides_output_before_releasing_own_display(app):
    controller, _, events = setup_controller(app)
    controller.start('hdr')
    lease = controller.lease
    original = lease.release
    def release():
        assert controller.output.isHidden()
        original()
    lease.release = release
    controller.stop()
    controller.stop()
    assert events.count('release') == 1
    assert events.index('audio-stop') < events.index('release')


def test_target_removal_stops_capture_and_hides_output(app):
    controller, sources, _ = setup_controller(app)
    controller.start('hdr')
    worker = controller.worker
    sources.pop()
    controller.verify_displays()
    assert not worker.isRunning()
    assert not controller.running
    assert controller.output.isHidden()


def test_transient_release_error_keeps_lease_for_retry(app):
    controller, _, events = setup_controller(app)
    controller.start('hdr')
    lease = controller.lease
    original = lease.release
    lease.release = lambda: (_ for _ in ()).throw(RuntimeError('temporary detach error'))
    assert not controller.stop()
    assert controller.lease is lease
    assert controller.output.isHidden()
    lease.release = original
    assert controller.stop()
    assert controller.lease is None
    assert events.count('release') == 1
