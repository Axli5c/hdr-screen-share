"""Terminate only a probe-owned app process and verify its output disappears."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

from hdr_share.monitors import list_sources
from hdr_share.virtual_display import WindowsDisplayBackend


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', type=Path)
    args = parser.parse_args()
    backend = WindowsDisplayBackend()
    identity = backend.owned_display()
    if not backend.registered() or (identity is not None and backend.snapshot(identity).active):
        raise RuntimeError('Close the running app before the crash probe')
    before = list_sources()
    command = [str(args.exe.resolve())] if args.exe else [sys.executable, '-m', 'hdr_share']
    process = subprocess.Popen(command + ['--mode', 'screen', '--smoke-seconds', '60'],
                               creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        deadline = time.monotonic() + 12
        def active():
            current = backend.owned_display()
            return current is not None and backend.snapshot(current).active
        while time.monotonic() < deadline and not active():
            if process.poll() is not None:
                raise RuntimeError('Probe app exited before creating its output')
            time.sleep(.1)
        if not active():
            raise RuntimeError('Probe output was not created')
        time.sleep(.8)
        process.terminate()
        process.wait(timeout=5)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and backend.owned_display() is not None:
            time.sleep(.1)
        result = {'adapter_absent_after_crash': backend.owned_display() is None,
                  'physical_topology_restored': list_sources() == before}
        print(json.dumps(result))
        return 0 if all(result.values()) else 1
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)


if __name__ == '__main__':
    raise SystemExit(main())
