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
    class Presenter:
        def __init__(self, hwnd, width, height): events.append('presenter-open')
        def present(self, pixels): events.append('present')
        def close(self): events.append('presenter-close')
    controller = StreamController(sources=lambda: sources, lease_factory=lambda *args: Lease(),
        audio_factory=lambda: Audio(), worker_factory=factory,
        screen_lookup=lambda _: app.primaryScreen(),
        output_factory=lambda: OutputWindow(presenter_factory=Presenter))
    return controller, sources, events


def test_audio_failure_leaves_video_with_visible_error(app):
    controller, _, events = setup_controller(app, bad_audio=True)
    controller.start('hdr')
    assert controller.running
    assert 'audio unavailable' in controller.audio_status
    controller.stop()
    assert events.count('release') == 0


def test_virtual_screen_uses_discord_audio_without_relay(app):
    controller, _, events = setup_controller(app, bad_audio=True)
    controller.start('hdr', mode='screen')
    assert controller.running
    assert controller.audio is None
    assert controller.audio_status == 'Audio: Discord system audio'
    assert 'audio-start' not in events and 'audio-stop' not in events
    controller.stop()


def test_application_mode_keeps_filtered_audio(app):
    controller, _, events = setup_controller(app)
    controller.start('hdr', mode='application')
    assert controller.audio is not None
    assert 'audio-start' in events
    controller.stop()


def test_display_failure_is_retryable(app):
    controller, _, _ = setup_controller(app, bad_display=True)
    controller.start('hdr', mode='screen')
    assert not controller.running
    assert controller.output.isHidden()
    assert 'display unavailable' in controller.video_status
    controller.stop()


def test_stop_hides_output_before_releasing_own_display(app):
    controller, _, events = setup_controller(app)
    controller.start('hdr', mode='screen')
    lease = controller.lease
    original = lease.release
    def release():
        assert controller.output.isHidden()
        original()
    lease.release = release
    controller.stop()
    controller.stop()
    assert events.count('release') == 1
    assert 'audio-start' not in events


def test_target_removal_stops_capture_and_hides_output(app):
    controller, sources, _ = setup_controller(app)
    controller.start('hdr', mode='screen')
    worker = controller.worker
    sources.pop()
    controller.verify_displays()
    assert not worker.isRunning()
    assert not controller.running
    assert controller.output.isHidden()


def test_transient_release_error_keeps_lease_for_retry(app):
    controller, _, events = setup_controller(app)
    controller.start('hdr', mode='screen')
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


def test_application_capture_works_with_one_monitor_and_never_acquires_display(app):
    controller, sources, events = setup_controller(app)
    sources.pop()
    def forbidden(*args): raise AssertionError('Application mode must not request a display/UAC')
    controller.lease_factory = forbidden
    controller.start('hdr', mode='application')
    try:
        assert controller.running and controller.lease is None
        assert controller.display_status == 'Display: application window'
        controller.verify_displays()
        assert controller.running
        controller.frames.put(np.full((2160, 3840, 4), 70, np.uint8))
        controller.present_latest()
        assert controller.output.output_size == (3840, 2160)
        assert 'present' in events and controller.output.presented > 0
    finally:
        controller.stop()
    assert 'presenter-close' in events and 'audio-stop' in events
    assert 'acquire' not in events and 'release' not in events


def test_application_to_screen_switch_closes_renderer_before_display_acquire(app):
    controller, _, events = setup_controller(app)
    controller.start('hdr', mode='application')
    controller.frames.put(np.zeros((8, 16, 4), np.uint8))
    controller.present_latest()
    controller.start('hdr', mode='screen')
    try:
        assert controller.running and controller.lease is not None
        assert events.index('presenter-close') < events.index('acquire')
    finally:
        controller.stop()


def test_gpu_output_failure_stops_application_capture_and_audio(app):
    controller, _, events = setup_controller(app)
    def broken(*args): raise RuntimeError('GPU unavailable')
    controller.output._presenter_factory = broken
    controller.start('hdr', mode='application')
    worker = controller.worker
    controller.frames.put(np.zeros((8, 16, 4), np.uint8))
    controller.present_latest()
    assert not controller.running and not worker.isRunning()
    assert controller.output.isHidden() and controller.audio is None
    assert 'GPU unavailable' in controller.video_status
    assert 'audio-stop' in events and 'acquire' not in events
