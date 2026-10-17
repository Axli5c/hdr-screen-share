"""Synthetic-only spectral acceptance helper, no persistence of captured audio."""
import numpy as np


def analyze_tones(samples, sample_rate=48000):
    mono = np.asarray(samples, dtype=np.float64)
    if mono.ndim == 2:
        mono = mono.mean(axis=1)
    if mono.ndim != 1 or len(mono) < sample_rate:
        raise ValueError('At least one second of mono/stereo audio is required')
    window = np.hanning(len(mono))
    spectrum = np.abs(np.fft.rfft(mono * window)) * 2 / window.sum()
    frequencies = np.fft.rfftfreq(len(mono), 1 / sample_rate)
    def amplitude(frequency):
        return float(spectrum[np.abs(frequencies - frequency) <= 3].max())
    first, second, excluded = (amplitude(frequency) for frequency in (700, 1100, 1700))
    reference = min(first, second)
    excluded_db = float(20 * np.log10(max(excluded, 1e-15) / max(reference, 1e-15)))
    return {'allowed_amplitudes': [first, second], 'excluded_amplitude': excluded,
            'excluded_db': excluded_db,
            'passed': reference > 0.001 and excluded_db <= -60}
