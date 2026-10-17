"""Orchestrate the owned display, video and audio with ordered cleanup."""
import time

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from .audio import AudioRelay, NativeAudioBridge
from .capture import CaptureWorker
from .frames import FrameMailbox, fit_size
from .monitors import list_sources
from .virtual_display import DisplayLease


def open_audio():
    bridge = NativeAudioBridge()
    candidates = [item for item in bridge.endpoints()
                  if 'CABLE Input' in item['name'] and 'VB-Audio' in item['name']]
    if len(candidates) != 1:
        raise RuntimeError('VB-CABLE is not installed.')
    if candidates[0]['default_roles']:
        raise RuntimeError('Set your headphones as the default Windows output.')
    return AudioRelay(candidates[0]['id'], bridge=bridge)


class StreamController(QObject):
    changed = Signal()

    def __init__(self, *, sources=list_sources, lease_factory=DisplayLease,
                 audio_factory=open_audio, worker_factory=CaptureWorker,
                 screen_lookup=None, output_factory=None):
        super().__init__()
        from .ui import OutputWindow, screen_for_source
        self.sources, self.lease_factory = sources, lease_factory
        self.audio_factory, self.worker_factory = audio_factory, worker_factory
        self.screen_lookup = screen_lookup or screen_for_source
        self.output = (output_factory or OutputWindow)()
        self.frames = FrameMailbox()
        self.worker = self.lease = self.audio = None
        self.running = self.starting = False
        self.video_status = 'Ready'
        self.audio_status = 'Audio: off'
        self.display_status = 'Display: off'
        self._source_id = self._target_id = None
        self._topology = ()
        self._sequence = 0

    @staticmethod
    def topology(sources, source_id, target_id):
        selected = [source for source in sources if source.id in (source_id, target_id)]
        if source_id == target_id or len(selected) != 2:
            raise RuntimeError('Display unavailable')
        return tuple((s.id, s.index, s.left, s.top, s.width, s.height, s.hdr_enabled)
                     for s in sorted(selected, key=lambda s: s.id))

    def start(self, source_id, mode="application"):
        if mode not in ("screen", "application"):
            raise ValueError("Unknown share mode")
        self.mode = mode
        if not self.stop():
            return
        self.starting = True
        self.video_status = 'Starting…'
        self.audio_status = 'Audio: starting…' if mode == 'application' else 'Audio: Discord system audio'
        self.display_status = 'Display: connecting…'
        self.changed.emit()
        self.frames = FrameMailbox()
        self._sequence = 0
        self._source_id = source_id
        try:
            source = next((s for s in self.sources() if s.id == source_id), None)
            if source is None:
                raise RuntimeError('Source disconnected')
            self.lease = self.lease_factory(source_id, *fit_size(source.width, source.height))
            target = self.lease.acquire()
            self._target_id = target.id
            self.target_number = target.index + 1
            self.display_status = f'Display: Screen {self.target_number} · connected'
            # Flush the screen-added notification while startup ignores topology events.
            QApplication.processEvents()
            screen = self.screen_lookup(target.id)
            if screen is None:
                raise RuntimeError('Virtual display unavailable')
            self._topology = self.topology(self.sources(), source_id, target.id)
            self.output.place_on(screen)
            ratio = screen.devicePixelRatio()
            self.output.setFixedSize(max(1, round(target.width / ratio)), max(1, round(target.height / ratio)))
            self.output.move(screen.geometry().topLeft())
            self.output.show()
            self.worker = self.worker_factory(source_id, self.frames)
            worker = self.worker
            worker.ready.connect(lambda hdr: self._ready(worker, hdr))
            worker.failed.connect(lambda message: self._error(worker, message))
            worker.finished.connect(lambda: self._finished(worker))
            self.running = True
            self.video_status = 'Starting…'
            worker.start()
            if mode == "application":
                try:
                    self.audio = self.audio_factory()
                    self.audio.start()
                    self.audio_status = 'Audio: filtered app mix'
                except Exception as error:
                    if self.audio is not None:
                        self.audio.stop()
                        self.audio = None
                    self.audio_status = f'Audio unavailable: {error}'
            else:
                self.audio_status = "Audio: Discord system audio"
        except Exception as error:
            self.stop()
            self.video_status = f'Error: {error}'
        finally:
            self.starting = False
            self.changed.emit()

    def _ready(self, worker, hdr):
        if worker is self.worker and self.running:
            self.video_status = 'HDR → SDR · Running' if hdr else 'SDR · Running'
            self.changed.emit()

    def _error(self, worker, message):
        if worker is self.worker:
            self.video_status = f'Capture error: {message}'
            self.output.hide()
            self.changed.emit()

    def _finished(self, worker):
        if worker is self.worker:
            message = self.video_status
            self.stop()
            self.video_status = message
            self.changed.emit()

    def stop(self):
        self.output.hide()
        self.running = False
        if self.audio is not None:
            self.audio.stop()
            self.audio = None
        if self.worker is not None:
            self.worker.request_stop()
            if not self.worker.wait(3000):
                self.video_status = 'Stopping…'
                self.changed.emit()
                return False
            worker, self.worker = self.worker, None
            worker.deleteLater()
        if self.lease is not None:
            try:
                self.lease.release()
                self.lease = None
            except Exception as error:
                self.video_status = f'Display cleanup failed: {error}'
                self.display_status = f'Display: cleanup failed · {error}'
                self.changed.emit()
                return False
        self.frames.clear()
        self.video_status = 'Ready'
        self.audio_status = 'Audio: off'
        self.display_status = 'Display: off'
        self.changed.emit()
        return True

    def display_changed(self, *args):
        if self.running and not self.starting:
            self.output.hide()
            self.stop()
            self.video_status = 'Displays changed. Refresh to restart.'
            self.changed.emit()

    def verify_displays(self):
        if not self.running or self.starting:
            return
        try:
            if self.topology(self.sources(), self._source_id, self._target_id) != self._topology:
                self.display_changed()
        except Exception:
            self.display_changed()
        if self.audio is not None and self.audio.last_error:
            self.audio_status = f'Audio unavailable: {self.audio.last_error}'
            self.changed.emit()
        elif self.audio is not None:
            self.audio_status = 'Audio: filtered app mix'

            self.changed.emit()

    def present_latest(self):
        if not self.running:
            return
        item = self.frames.latest_after(self._sequence)
        if item is not None:
            self._sequence, pixels, _ = item
            self.output.set_frame(pixels)
