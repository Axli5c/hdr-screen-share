import json

from hdr_share import devices


class Display:
    def __init__(self, registered=True, problem=22):
        self.present = registered
        self.problem = problem

    def registered(self): return self.present
    def problem_code(self): return self.problem


class Audio:
    def __init__(self, roles=0, present=True):
        self.roles, self.present = roles, present

    def endpoints(self):
        return ([{'id': 'cable', 'name': 'CABLE Input (VB-Audio Virtual Cable)',
                  'default_roles': self.roles}] if self.present else [])

    def inactive_endpoints(self): return []


def test_disabled_cable_requires_enabling_not_reinstallation():
    class Disabled(Audio):
        def inactive_endpoints(self):
            return [{'id': 'disabled', 'name': 'CABLE Input (VB-Audio Virtual Cable)', 'default_roles': 0}]
    result = devices.dependency_statuses(display_backend=Display(), audio_bridge=Disabled(present=False))
    assert result[1].state == 'configure'
    assert 'enable' in result[1].detail.lower()


def test_disabled_owned_display_is_ready_but_broken_driver_is_not():
    result = devices.dependency_statuses(display_backend=Display(), audio_bridge=Audio())
    assert [item.state for item in result] == ['ready', 'ready']
    result = devices.dependency_statuses(display_backend=Display(problem=28), audio_bridge=Audio())
    assert result[0].state == 'error'
    assert not result[0].ready and '28' in result[0].detail
    assert result[1].ready


def test_missing_components_and_wrong_audio_default_are_distinct():
    result = devices.dependency_statuses(display_backend=Display(False), audio_bridge=Audio(present=False))
    assert [item.state for item in result] == ['missing', 'missing']
    result = devices.dependency_statuses(display_backend=Display(), audio_bridge=Audio(roles=7))
    assert result[1].state == 'configure'
    assert not result[1].ready


def test_probe_error_preserves_other_component_result():
    class BrokenAudio:
        def endpoints(self): raise OSError('Audio service unavailable')
    result = devices.dependency_statuses(display_backend=Display(), audio_bridge=BrokenAudio())
    assert result[0].ready
    assert result[1].state == 'error'
    assert 'Audio service' in result[1].detail


def test_restart_report_cannot_turn_into_green_until_next_boot(tmp_path):
    report = tmp_path / 'report.json'
    report.write_text(json.dumps({'created_at': 200, 'results': [
        {'component': 'vbcable', 'restart': True, 'state': 'installed'}]}))
    result = devices.dependency_statuses(display_backend=Display(), audio_bridge=Audio(),
                                       reports=[report], boot_time=100)
    assert result[1].state == 'restart'
    retry = tmp_path / 'retry.json'
    retry.write_text(json.dumps({'created_at': 220, 'results': [
        {'component': 'vbcable', 'restart': False, 'state': 'already-installed'}]}))
    result = devices.dependency_statuses(display_backend=Display(), audio_bridge=Audio(),
                                       reports=[report, retry], boot_time=100)
    assert result[1].state == 'restart'
    result = devices.dependency_statuses(display_backend=Display(), audio_bridge=Audio(),
                                       reports=[report], boot_time=300)
    assert result[1].ready
    report.write_text('incomplete')
    result = devices.dependency_statuses(display_backend=Display(False), audio_bridge=Audio(),
                                       reports=[report], boot_time=100)
    assert result[0].state == 'missing'
