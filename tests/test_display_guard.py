from hdr_share.display_guard import recover_output
from hdr_share.virtual_display import DisplayState
import base64
import json
import pytest


ACTIVE = DisplayState(True, 2560, 0, 2560, 1440, 60, 32, 0)


class Backend:
    def __init__(self):
        self.current = ACTIVE
        self.claimed = False
    def claim(self): self.claimed = True
    def unclaim(self): self.claimed = False
    def owned_display(self): return 'own'
    def snapshot(self, identity): return self.current
    def restore(self, identity, state): self.current = state


def test_guard_detaches_only_matching_owned_output():
    backend = Backend()
    assert recover_output(backend, 'own', ACTIVE)
    assert not backend.current.active
    assert not backend.claimed


def test_guard_removes_owned_screen_even_if_its_mode_changed():
    backend = Backend()
    changed = DisplayState(True, 2560, 0, 1920, 1080, 60, 32, 0)
    backend.current = changed
    assert recover_output(backend, 'own', ACTIVE)
    assert not backend.current.active
    assert not backend.claimed


def test_guard_does_not_touch_foreign_display():
    backend = Backend()
    assert not recover_output(backend, 'foreign', ACTIVE)
    assert backend.current == ACTIVE


@pytest.mark.parametrize('birth,wait_state,busy,expected', [
    (999, 1, False, []), (123, 1, False, [True, False]),
    (123, 0, False, [True, False]), (123, 0, True, [True, False]),
    (123, 1, True, [True, False])])
def test_elevated_guard_checks_parent_and_preserves_new_session(monkeypatch, birth, wait_state, busy, expected):
    from hdr_share import display_guard as guard
    from hdr_share.virtual_display import DisplayLeaseError
    class Kernel:
        def OpenProcess(self, *args): return 10
        def OpenEventW(self, *args): return 20
        def WaitForSingleObject(self, *args): return 258
        def WaitForMultipleObjects(self, *args): return wait_state
        def SetEvent(self, *args): return True
        def CloseHandle(self, *args): pass
    class Display:
        attempts = 0
        def claim(self):
            self.attempts += 1
            if busy and self.attempts == 1: raise DisplayLeaseError('another session')
        def unclaim(self): pass
    operations = []
    monkeypatch.setattr(guard, 'device_kernel', Kernel)
    monkeypatch.setattr(guard, 'WindowsDisplayBackend', Display)
    monkeypatch.setattr(guard, 'creation_time', lambda *args: birth)
    monkeypatch.setattr(guard, 'control_owned_device', operations.append)
    monkeypatch.setattr(guard.time, 'sleep', lambda _: None)
    payload = base64.urlsafe_b64encode(json.dumps({'pid': 42, 'birth': 123, 'nonce': 'a' * 32}).encode())
    guard.run_device_guard(payload)
    assert operations == expected


def test_failed_device_removal_is_not_reported_as_success():
    from hdr_share.display_guard import ElevatedDisplayGuard
    from hdr_share.virtual_display import DisplayLeaseError
    class Kernel:
        def SetEvent(self, *args): pass
        def WaitForSingleObject(self, *args): return 0
        def GetExitCodeProcess(self, process, code):
            code._obj.value = 1
            return True
        def CloseHandle(self, *args): pass
    guard = ElevatedDisplayGuard.__new__(ElevatedDisplayGuard)
    guard.kernel = Kernel()
    guard.ready, guard.stop, guard.process, guard.failed, guard.deferred = 1, 2, 3, 4, 5
    guard.kernel.WaitForMultipleObjects = lambda *args: 0
    with pytest.raises(DisplayLeaseError, match='cleanup failed'):
        guard.cancel()


def test_temporary_device_removal_failure_retries_in_live_helper(monkeypatch):
    from hdr_share import display_guard as guard
    from hdr_share.virtual_display import DisplayLeaseError
    attempts = []
    def disable(enabled):
        attempts.append(enabled)
        if len(attempts) == 1:
            raise DisplayLeaseError('temporary device busy')
    monkeypatch.setattr(guard, 'control_owned_device', disable)
    monkeypatch.setattr(guard.time, 'sleep', lambda _: None)
    guard.remove_owned_device()
    assert attempts == [False, False]


def test_cleanup_waits_for_unfinished_uac_session_instead_of_orphaning_adapter(monkeypatch):
    from hdr_share import display_guard as guard
    from hdr_share.virtual_display import DisplayLeaseError
    events = []
    class Display:
        def claim(self):
            events.append('claim')
            if events.count('claim') == 1: raise DisplayLeaseError('new UAC session pending')
    class Kernel:
        def SetEvent(self, handle): events.append('deferred')
    monkeypatch.setattr(guard.time, 'sleep', lambda _: events.append('wait'))
    guard.claim_cleanup_lease(Display(), Kernel(), 5)
    assert events == ['claim', 'deferred', 'wait', 'claim']
