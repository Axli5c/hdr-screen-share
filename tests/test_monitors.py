import pytest

from hdr_share.monitors import CaptureSource, default_source, hdr_from_info


def source(index, primary=False, hdr=None):
    return CaptureSource(str(index), f"Display {index}", primary, hdr, 3840, 2160, index)


def test_primary_sdr_does_not_displace_hdr_monitor():
    assert default_source([source(0, True, False), source(1, False, True)]).id == "1"


def test_primary_hdr_wins_over_first_hdr():
    assert default_source([source(1, False, True), source(2, True, True)]).id == "2"


def test_no_hdr_falls_back_to_primary_and_unknown_stays_unknown():
    assert default_source([source(0), source(1, True, False)]).id == "1"
    assert hdr_from_info(None, None) is None
    # WCG active is not HDR; modern activeColorMode is authoritative.
    assert hdr_from_info(1, 3) is False
    assert hdr_from_info(2, 0) is True
    assert hdr_from_info(None, 2) is True
    assert hdr_from_info(None, 0) is False


def test_missing_displays_is_actionable_error():
    with pytest.raises(RuntimeError, match="монитор"):
        default_source([])
