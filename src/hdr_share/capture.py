import logging
import time
from threading import Event

import numpy as np
from PySide6.QtCore import QThread, Signal

from .frames import LatestFrame, FrameMailbox
from .monitors import list_sources


def open_session(index: int, mode: str):
    import hdrcapture
    return hdrcapture.capture.monitor(index, mode=mode)


def unmapped_preview(raw):
    """Small scRGB preview with clipped highlights, without HDR tone mapping."""
    height, width, _ = raw.shape
    scale = min(1, 480 / width, 270 / height)
    rows = np.linspace(0, height - 1, max(1, round(height * scale))).astype(int)
    columns = np.linspace(0, width - 1, max(1, round(width * scale))).astype(int)
    rgb = np.array(raw[rows[:, None], columns[None, :], :3], dtype=np.float32)
    rgb = np.clip(np.nan_to_num(rgb, nan=0, posinf=1, neginf=0), 0, 1)
    srgb = np.where(rgb <= .0031308, rgb * 12.92, 1.055 * rgb ** (1 / 2.4) - .055)
    pixels = np.empty((*srgb.shape[:2], 4), np.uint8)
    pixels[:, :, :3] = np.rint(srgb[:, :, ::-1] * 255).astype(np.uint8)
    pixels[:, :, 3] = 255
    return pixels


class CaptureWorker(QThread):
    ready = Signal(bool)
    failed = Signal(str)

    def __init__(self, source_id: str, frames: LatestFrame, *,
                 sources=list_sources, factory=open_session):
        super().__init__()
        self.source_id = source_id
        self.frames = frames
        self._sources = sources
        self._factory = factory
        self._stop = Event()
        self.last_error = ""
        self.captured = 0
        self.duplicates = 0
        self.last_frame_at = 0.0
        self.started_at = 0.0
        self.frame_size = (0, 0)
        self._comparison_enabled = Event()
        self.comparison_frames = FrameMailbox()
        self.comparison_status = 'Off'

    def set_comparison_enabled(self, enabled):
        if enabled:
            self._comparison_enabled.set()
        else:
            self._comparison_enabled.clear()

    def request_stop(self):
        self._stop.set()

    def run(self):
        session = None
        raw_session = None
        comparison_failed = False
        comparison_at = 0
        try:
            source = next((s for s in self._sources() if s.id == self.source_id), None)
            if source is None:
                raise RuntimeError("Source disconnected. Refresh displays.")
            session = self._factory(source.index, mode="auto")
            actual_hdr = session.is_hdr
            if source.hdr_enabled is not None and source.hdr_enabled != actual_hdr:
                raise RuntimeError("HDR mode changed. Restart capture.")
            self.started_at = time.monotonic()
            deadline = self.started_at
            topology_at = deadline + 1
            last_timestamp = None
            while not self._stop.is_set():
                frame = session.grab()
                now = time.monotonic()
                if frame.timestamp != last_timestamp:
                    if frame.format != "bgra8":
                        raise RuntimeError("HDR conversion failed")
                    self.frames.put(frame.ndarray())
                    self.frame_size = (frame.width, frame.height) if hasattr(frame, "width") else (0, 0)
                    self.captured += 1
                    if self.captured == 1:
                        self.ready.emit(actual_hdr)
                    self.last_frame_at = now
                    last_timestamp = frame.timestamp
                else:
                    self.duplicates += 1
                if not self._comparison_enabled.is_set():
                    if raw_session is not None:
                        try:
                            raw_session.close()
                        except Exception:
                            logging.exception('Comparison capture close failed')
                        raw_session = None
                    self.comparison_frames.clear()
                    self.comparison_status = 'Off'
                    comparison_failed = False
                elif not comparison_failed and now >= comparison_at:
                    comparison_at = now + .2
                    try:
                        self.comparison_status = 'Starting…'
                        if raw_session is None:
                            raw_session = self._factory(source.index, mode='hdr')
                        raw = raw_session.grab()
                        if raw.format != 'rgba16f':
                            raise RuntimeError('Raw HDR format unavailable')
                        self.comparison_frames.put(unmapped_preview(raw.ndarray()))
                        self.comparison_status = 'Live'
                    except Exception as error:
                        comparison_failed = True
                        self.comparison_status = f'Unavailable: {error}'
                        self.comparison_frames.clear()
                        if raw_session is not None:
                            try:
                                raw_session.close()
                            except Exception:
                                logging.exception('Comparison capture close failed')
                            raw_session = None
                if now >= topology_at:
                    current = next((s for s in self._sources() if s.id == self.source_id), None)
                    if current is None:
                        raise RuntimeError("Source disconnected. Refresh displays.")
                    if current.index != source.index or current.hdr_enabled != source.hdr_enabled:
                        raise RuntimeError("Displays changed. Restart capture.")
                    topology_at = now + 1
                deadline += 1 / 60
                if deadline < time.monotonic():
                    deadline = time.monotonic()
                self._stop.wait(max(0, deadline - time.monotonic()))
        except Exception as exc:
            self.last_error = str(exc)
            logging.exception("Capture failed")
            self.failed.emit(self.last_error)
        finally:
            if raw_session is not None:
                try:
                    raw_session.close()
                except Exception:
                    logging.exception('Comparison capture close failed')
            if session is not None:
                try:
                    session.close()
                except Exception:
                    logging.exception("Capture close failed")
