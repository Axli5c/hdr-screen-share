import os
from pathlib import Path

import pytest

from hdr_share.audio import AudioError, AudioRelay, NativeAudioBridge
from hdr_share.audio_policy import ProcessIdentity as P


class Bridge:
    def __init__(self):
        self.events = []
        self.rows = [P(os.getpid(), 0, 1, 'hdr.exe'), P(300, 0, 1, 'game.exe')]
        self.active = {300}

    def open(self, endpoint):
        self.events.append(('open', endpoint))
        return 12

    def close(self, handle):
        self.events.append(('close', handle))

    def processes(self): return self.rows
    def audio_pids(self): return self.active
    def set_sources(self, handle, sources):
        self.events.append(('sources', [p.pid for p in sources]))
    def stats(self, handle): return {'last_hresult': 0, 'output_frames': 0}


def test_missing_native_module_has_actionable_error(tmp_path):
    with pytest.raises(AudioError, match='audio_bridge.dll'):
        NativeAudioBridge(tmp_path / 'audio_bridge.dll')


def test_relay_lifecycle_closes_once_and_does_not_open_microphone():
    bridge = Bridge()
    relay = AudioRelay('exact-cable-endpoint', bridge=bridge, refresh_interval=10)
    relay.start()
    relay.start()
    relay.stop()
    relay.stop()
    assert bridge.events == [('open', 'exact-cable-endpoint'), ('sources', [300]), ('close', 12)]


def test_unsafe_policy_mutes_existing_capture_before_error():
    bridge = Bridge()
    relay = AudioRelay('cable', bridge=bridge, refresh_interval=10)
    relay.start()
    bridge.rows.append(P(301, 300, 2, 'Discord.exe'))
    with pytest.raises(AudioError, match='excluded'):
        relay.refresh()
    relay.stop()
    assert bridge.events[-2:] == [('sources', []), ('close', 12)]


def test_partial_start_failure_releases_native_handle():
    bridge = Bridge()
    bridge.active = {999}
    relay = AudioRelay('cable', bridge=bridge)
    with pytest.raises(AudioError, match='Unknown'):
        relay.start()
    assert bridge.events[-1] == ('close', 12)
