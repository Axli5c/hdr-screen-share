import pytest

from hdr_share.monitors import CaptureSource
from hdr_share.virtual_display import DisplayLease, DisplayLeaseError


def test_adapter_interface_matches_exact_owned_instance():
    from hdr_share.virtual_display import is_owned_adapter_path
    assert is_owned_adapter_path(r'\\?\ROOT#HDRSCREENSHAREVDD#0000#{some-guid}')
    assert not is_owned_adapter_path(r'\\?\ROOT#HDRSCREENSHAREVDD#0001#{some-guid}')
    assert not is_owned_adapter_path(r'\\?\ROOT#MTTVDD#0000#{some-guid}')


class Desktop:
    def __init__(self, owned=True):
        self.owned = owned
        self.current = 'detached'
        self.events = []
        self.claimed = False

    def claim(self):
        if self.claimed:
            raise DisplayLeaseError('already owned')
        self.claimed = True

    def unclaim(self):
        self.claimed = False

    def owned_display(self):
        return 'device-owned' if self.owned else None

    def snapshot(self, identity):
        return self.current

    def attach(self, identity, width, height):
        self.events.append(('attach', identity, width, height))
        self.current = ('active', width, height)
        return CaptureSource(identity, 'Virtual SDR', False, False, width, height, 2)

    def restore(self, identity, before):
        self.events.append(('restore', identity))
        self.current = before


def test_foreign_vdd_is_not_claimed():
    api = Desktop(owned=False)
    with pytest.raises(DisplayLeaseError, match='owned'):
        DisplayLease('physical', 3840, 2160, backend=api).acquire()
    assert api.events == []


def test_release_does_not_overwrite_user_topology():
    api = Desktop()
    lease = DisplayLease('physical', 3840, 2160, backend=api)
    assert lease.acquire().width == 3840
    api.current = ('user-selected', 1920, 1080)
    lease.release()
    assert api.current == ('user-selected', 1920, 1080)
    assert len(api.events) == 1


def test_release_is_idempotent():
    api = Desktop()
    lease = DisplayLease('physical', 3840, 2160, backend=api)
    lease.acquire()
    lease.release()
    lease.release()
    assert api.current == 'detached'
    assert [event[0] for event in api.events] == ['attach', 'restore']


def test_acquire_twice_does_not_replace_original_snapshot():
    api = Desktop()
    lease = DisplayLease('physical', 3840, 2160, backend=api)
    assert lease.acquire() is lease.acquire()
    lease.release()
    assert api.current == 'detached'


def test_source_cannot_be_owned_output():
    api = Desktop()
    with pytest.raises(DisplayLeaseError):
        DisplayLease('device-owned', 3840, 2160, backend=api).acquire()
    assert api.events == []


def test_second_lease_cannot_disconnect_running_first_lease():
    api = Desktop()
    first = DisplayLease('physical', 3840, 2160, backend=api)
    second = DisplayLease('physical', 3840, 2160, backend=api)
    first.acquire()
    with pytest.raises(DisplayLeaseError, match='owned'):
        second.acquire()
    second.release()
    assert api.current == ('active', 3840, 2160)
    first.release()
    assert not api.claimed


def test_failed_acquire_releases_claim():
    api = Desktop(owned=False)
    lease = DisplayLease('physical', 3840, 2160, backend=api)
    with pytest.raises(DisplayLeaseError):
        lease.acquire()
    assert not api.claimed


def test_native_lock_rejects_second_backend_on_same_thread():
    from hdr_share.virtual_display import WindowsDisplayBackend
    first, second = WindowsDisplayBackend(), WindowsDisplayBackend()
    first.claim()
    try:
        with pytest.raises(DisplayLeaseError, match='owned'):
            second.claim()
    finally:
        second.unclaim()
        first.unclaim()
