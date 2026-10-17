from threading import Lock
import time

import numpy as np


def fit_size(width: int, height: int) -> tuple[int, int]:
    if width <= 0 or height <= 0:
        raise ValueError("Frame dimensions must be positive")
    maximum = (3840, 2160) if width >= height else (2160, 3840)
    scale = min(1.0, maximum[0] / width, maximum[1] / height)
    return max(1, round(width * scale)), max(1, round(height * scale))


class LatestFrame:
    """A single owned BGRA frame; a slow consumer never builds a backlog."""

    def __init__(self):
        self._lock = Lock()
        self._frame = None

    def put(self, frame: np.ndarray) -> None:
        owned = np.array(frame, dtype=np.uint8, copy=True, order="C")
        with self._lock:
            self._frame = owned

    def take(self) -> np.ndarray | None:
        with self._lock:
            frame, self._frame = self._frame, None
        return frame


class FrameMailbox:
    """One immutable current frame with independent reader sequence numbers."""
    def __init__(self):
        self._lock = Lock()
        self._sequence = 0
        self._current = None

    def publish(self, frame: np.ndarray, timestamp: float) -> int:
        pixels = np.asarray(frame, dtype=np.uint8, order='C')
        owned = np.frombuffer(pixels.tobytes(), dtype=np.uint8).reshape(pixels.shape)
        with self._lock:
            self._sequence += 1
            self._current = (self._sequence, owned, timestamp)
            return self._sequence

    def put(self, frame: np.ndarray) -> None:
        self.publish(frame, time.monotonic())

    def latest_after(self, sequence: int):
        with self._lock:
            return self._current if self._current is not None and self._current[0] > sequence else None

    def clear(self):
        with self._lock:
            self._current = None
