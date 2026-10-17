"""Bounded synthetic WGC probe. Does not open Discord or record user content."""
import argparse
import json
import threading
import time

import numpy as np
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication

from hdr_share.monitors import default_source, enable_physical_pixels, list_sources
from hdr_share.ui import OutputWindow, match_screen
from hdr_share.virtual_display import DisplayLease


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seconds', type=int, default=6)
    parser.add_argument('--fps', type=int, default=4)
    parser.add_argument('--warmup', type=int, default=0)
    args = parser.parse_args()
    if not 3 <= args.seconds <= 75 or not 1 <= args.fps <= 60 or not 0 <= args.warmup <= 10:
        parser.error('seconds must be 3..75 and fps 1..60')
    enable_physical_pixels()
    before = list_sources()
    lease = DisplayLease(default_source(before).id, 3840, 2160)
    output = None
    stop = threading.Event()
    results = {'sizes': set(), 'colors': set(), 'frames': 0, 'unique_captures': 0, 'error': ''}
    worker = None
    try:
        target = lease.acquire()
        app = QApplication([])
        output = OutputWindow()
        screen = match_screen(target, app.screens())
        if screen is None:
            raise RuntimeError('Qt cannot identify the owned virtual screen')
        output.place_on(screen)
        colors = []
        for channel in (1, 2):
            pixels = np.zeros((2160, 3840, 4), dtype=np.uint8)
            pixels[:, :, channel] = 220
            pixels[:, :, 3] = 255
            colors.append(pixels)
        output.set_frame(colors[0])
        output.show()
        counter = [0]

        def change():
            counter[0] += 1
            output.set_frame(colors[counter[0] % 2])

        timer = QTimer()
        timer.setTimerType(Qt.TimerType.PreciseTimer)
        timer.timeout.connect(change)
        timer.start(max(1, int(1000 / args.fps)))
        hwnd = int(output.winId())

        def capture():
            session = None
            try:
                import hdrcapture
                session = hdrcapture.capture.window(hwnd=hwnd, mode='sdr')
                last_timestamp = None
                while not stop.is_set():
                    frame = session.grab()
                    if frame.timestamp != last_timestamp:
                        results['unique_captures'] += 1
                        last_timestamp = frame.timestamp
                    pixels = frame.ndarray()
                    results['sizes'].add((pixels.shape[1], pixels.shape[0]))
                    center = pixels[pixels.shape[0] // 2, pixels.shape[1] // 2, :3]
                    if int(center.max()) > 180:
                        results['colors'].add(int(center.argmax()))
                    results['frames'] += 1
            except Exception as error:
                results['error'] = str(error)
            finally:
                if session is not None:
                    session.close()

        worker = threading.Thread(target=capture, daemon=True)
        measure = {'started': time.monotonic(), 'presented': 0}
        def begin_measurement():
            measure['started'] = time.monotonic()
            measure['presented'] = output.presented
            results['frames'] = results['unique_captures'] = 0
        if args.warmup:
            QTimer.singleShot(args.warmup * 1000, begin_measurement)
        QTimer.singleShot(500, worker.start)
        finish_timer = QTimer()
        finish_timer.setSingleShot(True)
        finish_timer.setTimerType(Qt.TimerType.PreciseTimer)
        finish_timer.timeout.connect(app.quit)
        finish_timer.start((args.seconds + args.warmup) * 1000)
        app.exec()
        results['elapsed'] = time.monotonic() - measure['started']
        results['warmup_seconds'] = args.warmup
        results['presented'] = output.presented - measure['presented']
        results['render_fps'] = results['presented'] / results['elapsed']
        results['window_capture_fps'] = results['unique_captures'] / max(.001, results['elapsed'] - (0 if args.warmup else .5))
    finally:
        stop.set()
        if worker is not None and worker.ident is not None:
            worker.join(timeout=3)
        if output is not None:
            output.hide()
        lease.release()
    results['sizes'] = sorted(results['sizes'])
    results['colors'] = sorted(results['colors'])
    results['physical_unchanged'] = list_sources() == before
    results['passed'] = (results['sizes'] == [(3840, 2160)] and results['colors'] == [1, 2]
                         and results['physical_unchanged'] and not results['error'])
    print(json.dumps(results, ensure_ascii=True))
    return 0 if results['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
