import numpy as np


def test_mailbox_two_consumers_read_same_frame_independently():
    from hdr_share.frames import FrameMailbox
    box = FrameMailbox()
    original = np.zeros((2, 3, 4), np.uint8)
    sequence = box.publish(original, 1.5)
    first = box.latest_after(0)
    second = box.latest_after(0)
    assert first[0] == second[0] == sequence
    assert first[1] is second[1]
    assert first[2] == 1.5
    original[:] = 99
    assert not first[1].any()
    assert not first[1].flags.writeable
    assert box.latest_after(sequence) is None


def test_mailbox_slow_consumer_receives_only_latest():
    from hdr_share.frames import FrameMailbox
    box = FrameMailbox()
    for index in range(10):
        box.publish(np.full((2, 3, 4), index, np.uint8), float(index))
    sequence, frame, timestamp = box.latest_after(0)
    assert sequence == 10 and timestamp == 9
    assert np.all(frame == 9)
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
