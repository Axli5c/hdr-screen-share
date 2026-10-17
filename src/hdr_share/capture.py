import logging
import time
from threading import Event

from PySide6.QtCore import QThread, Signal

from .frames import LatestFrame
from .monitors import list_sources


def open_session(index: int, mode: str):
    import hdrcapture
    return hdrcapture.capture.monitor(index, mode=mode)


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

    def request_stop(self):
        self._stop.set()

    def run(self):
        session = None
        try:
            source = next((s for s in self._sources() if s.id == self.source_id), None)
            if source is None:
                raise RuntimeError("Выбранный монитор отключён. Обновите список мониторов.")
            session = self._factory(source.index, mode="auto")
            actual_hdr = session.is_hdr
            if source.hdr_enabled is not None and source.hdr_enabled != actual_hdr:
                raise RuntimeError("Режим HDR монитора изменился. Обновите список и запустите снова.")
            self.ready.emit(actual_hdr)
            self.started_at = time.monotonic()
            deadline = self.started_at
            topology_at = deadline + 1
            last_timestamp = None
            while not self._stop.is_set():
                frame = session.grab()
                now = time.monotonic()
                if frame.timestamp != last_timestamp:
                    if frame.format != "bgra8":
                        raise RuntimeError("HDR backend не вернул преобразованный SDR-кадр BGRA8")
                    self.frames.put(frame.ndarray())
                    self.frame_size = (frame.width, frame.height) if hasattr(frame, "width") else (0, 0)
                    self.captured += 1
                    self.last_frame_at = now
                    last_timestamp = frame.timestamp
                else:
                    self.duplicates += 1
                if now >= topology_at:
                    current = next((s for s in self._sources() if s.id == self.source_id), None)
                    if current is None:
                        raise RuntimeError("Выбранный монитор отключён. Обновите список.")
                    if current.index != source.index or current.hdr_enabled != source.hdr_enabled:
                        raise RuntimeError("Конфигурация мониторов изменилась. Запустите захват снова.")
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
            if session is not None:
                try:
                    session.close()
                except Exception:
                    logging.exception("Capture close failed")
