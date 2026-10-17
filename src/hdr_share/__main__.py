import argparse
import logging
import sys
import time
from pathlib import Path

from .monitors import enable_physical_pixels


def main():
    parser = argparse.ArgumentParser(description="HDR to SDR screen relay for Discord")
    parser.add_argument("--smoke-seconds", type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument("--diagnostics", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    import os
    logdir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "HDRScreenShare"
    logdir.mkdir(parents=True, exist_ok=True)
    from logging.handlers import RotatingFileHandler
    logging.basicConfig(level=logging.INFO, handlers=[RotatingFileHandler(
        logdir / "app.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")])
    enable_physical_pixels()
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from .ui import ControlWindow
    app = QApplication(sys.argv[:1])
    app.setApplicationName("HDR Screen Share")
    app.setQuitOnLastWindowClosed(False)
    window = ControlWindow()
    window.show()
    # Explicit quit follows successful worker shutdown, never the invisible output window.
    window.closed.connect(app.quit)
    if args.smoke_seconds:
        window.setEnabled(False)
        cpu_start = time.process_time()
        def finish():
            import json
            worker = window.worker
            data = {"captured": worker.captured if worker else 0,
                    "presented": window.output.presented,
                    "output_size": window.output.output_size,
                    "status": window.status.text(), "error": worker.last_error if worker else "",
                    "stats": window.stats.text()}
            data['audio_status'] = window.audio_status.text()
            data['audio_stats'] = window.controller.audio.stats() if window.controller.audio else None
            if worker and worker.started_at:
                elapsed = time.monotonic() - worker.started_at
                data.update(elapsed_seconds=elapsed, captured_fps=worker.captured / elapsed,
                            painted_fps=window.output.presented / elapsed,
                            cpu_seconds=time.process_time() - cpu_start,
                            source_id=worker.source_id)
            if args.diagnostics:
                args.diagnostics.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                window.grab().save(str(args.diagnostics.with_suffix(".png")))
            window.close()
        QTimer.singleShot(args.smoke_seconds * 1000, finish)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
