"""Synthetic process-filter probe. Brief tones play through the normal headphones.

Only the two helper process identities are relayed. The excluded helper is named
Discord.exe to exercise the same image-name rule as desktop Discord. No call or
Discord broadcast is started. Samples stay in memory and are never saved.
"""
import argparse
import ctypes as C
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import numpy as np

from hdr_share.audio import AudioError, NativeAudioBridge, _check
from hdr_share.audio_diagnostics import analyze_tones
from hdr_share.audio_policy import select_capture_roots


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--list', action='store_true', help='Only enumerate render endpoints')
    parser.add_argument('--worker-pids', type=int, nargs=3, help=argparse.SUPPRESS)
    parser.add_argument('--source-exit', action='store_true', help='Verify surviving audio when one source closes')
    args = parser.parse_args()
    bridge = NativeAudioBridge()
    endpoints = bridge.endpoints()
    if args.list:
        print(json.dumps(endpoints, ensure_ascii=True))
        return 0
    candidates = [item for item in endpoints if 'CABLE Input' in item['name'] and 'VB-Audio' in item['name']]
    if len(candidates) != 1:
        raise AudioError('Install the original VB-CABLE driver first; expected one CABLE Input endpoint')
    cable = candidates[0]
    if cable['default_roles']:
        raise AudioError('VB-CABLE is a default output. Restore your headphones in Windows before running the probe.')
    root = Path(__file__).resolve().parents[1]
    tone = root / 'build/native/tone.exe'
    if not tone.is_file():
        raise AudioError('Build the diagnostic helpers: ./build-native.ps1 -WithProbes')
    excluded = root / 'build/native/probe-excluded/Discord.exe'
    if args.worker_pids is None:
        excluded.parent.mkdir(exist_ok=True)
        shutil.copyfile(tone, excluded)
        handles = []
        try:
            for executable, frequency in ((tone, 700), (tone, 1100), (excluded, 1700)):
                duration = '3' if args.source_exit and frequency == 700 else '12'
                handles.append(subprocess.Popen([str(executable), str(frequency), duration],
                    creationflags=subprocess.CREATE_NO_WINDOW))
            # Relay and tone processes are siblings. Own-process descendants must
            # remain excluded, including when testing the real policy.
            command = [sys.executable, str(Path(__file__).resolve()), '--worker-pids',
                *(str(process.pid) for process in handles)]
            if args.source_exit:
                command.append('--source-exit')
            result = subprocess.run(command, capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW, timeout=25)
            print(result.stdout.strip())
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            return result.returncode
        finally:
            for process in handles:
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=5)
    relay = None
    try:
        time.sleep(0.5)
        identities = bridge.processes()
        roots = select_capture_roots(identities, set(args.worker_pids), os.getpid())
        if {item.pid for item in roots} != set(args.worker_pids[:2]):
            raise AudioError('Unexpected synthetic capture policy result')
        relay = bridge.open(cable['id'])
        bridge.set_sources(relay, roots)
        time.sleep(1)
        initial = bridge.stats(relay)
        _check(initial['last_hresult'])
        seconds = 4
        samples = np.zeros((seconds * 48000, 2), dtype=np.float32)
        written = C.c_uint32()
        probe = bridge.lib.ab_probe_capture
        probe.argtypes = [C.c_wchar_p, C.c_uint32, C.POINTER(C.c_float), C.c_uint32, C.POINTER(C.c_uint32)]
        probe.restype = C.c_int32
        _check(probe(cable['id'], seconds, samples.ctypes.data_as(C.POINTER(C.c_float)), len(samples), C.byref(written)))
        stats = bridge.stats(relay)
        _check(stats['last_hresult'])
        result = analyze_tones(samples[24000:written.value])
        if args.source_exit:
            tail = analyze_tones(samples[written.value - 48000:written.value])
            result['surviving_amplitude'] = tail['allowed_amplitudes'][1]
            result['passed'] = (result['surviving_amplitude'] > .001 and
                tail['excluded_amplitude'] < result['surviving_amplitude'] * .001)
        result['stats'] = stats
        result['defaults_unchanged'] = bridge.endpoints() == endpoints
        result['passed'] = result['passed'] and result['defaults_unchanged'] and stats['queued_frames'] <= 4800
        print(json.dumps(result, ensure_ascii=True))
        return 0 if result['passed'] else 1
    finally:
        if relay is not None:
            bridge.close(relay)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except AudioError as error:
        print(json.dumps({'passed': False, 'error': str(error)}, ensure_ascii=True))
        raise SystemExit(1)
