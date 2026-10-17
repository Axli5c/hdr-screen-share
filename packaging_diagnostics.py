"""Opt-in startup traces for diagnosing a frozen build before Qt imports."""
import atexit
import faulthandler
from pathlib import Path
import sys

if "--diagnostics" in sys.argv:
    index = sys.argv.index("--diagnostics") + 1
    if index < len(sys.argv):
        trace_path = Path(sys.argv[index]).with_suffix(".trace.log")
        try:
            trace_stream = trace_path.open("w", encoding="utf-8")
            faulthandler.enable(file=trace_stream)
            faulthandler.dump_traceback_later(10, repeat=True, file=trace_stream)
            atexit.register(faulthandler.cancel_dump_traceback_later)
        except OSError:
            pass
