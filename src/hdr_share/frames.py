from threading import Lock

import numpy as np


def fit_size(width: int, height: int) -> tuple[int, int]:
    if width <= 0 or height <= 0:
        raise ValueError("Размер кадра должен быть положительным")
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
