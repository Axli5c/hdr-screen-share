from hdr_share.display_guard import recover_output
from hdr_share.virtual_display import DisplayState


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
