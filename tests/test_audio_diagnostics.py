import numpy as np

from hdr_share.audio_diagnostics import analyze_tones


def signal(excluded=0):
    t = np.arange(48000 * 2) / 48000
    return 0.06 * np.sin(t * 2 * np.pi * 700) + 0.06 * np.sin(t * 2 * np.pi * 1100) + excluded * np.sin(t * 2 * np.pi * 1700)


def test_spectral_probe_accepts_two_permitted_tones():
    result = analyze_tones(signal())
    assert result['passed']
    assert result['excluded_db'] < -60


def test_spectral_probe_rejects_excluded_tone():
    assert not analyze_tones(signal(0.01))['passed']


def test_spectral_probe_rejects_missing_audio():
    assert not analyze_tones(np.zeros(48000))['passed']
