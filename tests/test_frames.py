import numpy as np
import pytest

from hdr_share.frames import LatestFrame, fit_size


@pytest.mark.parametrize("source,expected", [
    ((3840, 2160), (3840, 2160)), ((7680, 4320), (3840, 2160)),
    ((2160, 3840), (2160, 3840)), ((1080, 1920), (1080, 1920)),
    ((1280, 720), (1280, 720)), ((5120, 1440), (3840, 1080)),
])
def test_preserves_physical_resolution_and_aspect(source, expected):
    assert fit_size(*source) == expected


@pytest.mark.parametrize("size", [(0, 1), (1, -1)])
def test_rejects_invalid_size(size):
    with pytest.raises(ValueError):
        fit_size(*size)


def test_latest_frame_owns_data_and_does_not_build_queue():
    slot = LatestFrame()
    assert slot.take() is None
    source = np.zeros((2, 3, 4), dtype=np.uint8)
    slot.put(source)
    source[:] = 255
    assert slot.take().max() == 0
    slot.put(source)
    source[:] = 42
    slot.put(source)
    assert slot.take().min() == 42
    assert slot.take() is None
