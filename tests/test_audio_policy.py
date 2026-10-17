import pytest

from hdr_share.audio_policy import AudioPolicyError, ProcessIdentity as P, select_capture_roots


def roots(processes, active, own=100):
    return [p.pid for p in select_capture_roots(processes, set(active), own)]


def test_discord_variants_children_and_own_tree_are_excluded():
    processes = [P(100, 0, 1, 'hdr.exe'), P(101, 100, 2, 'helper.exe'),
                 P(200, 0, 1, 'Discord.exe'), P(201, 200, 2, 'renderer.exe'),
                 P(210, 0, 1, 'DiscordPTB.exe'), P(220, 0, 1, 'DiscordCanary.exe'),
                 P(300, 0, 1, 'game.exe'), P(400, 0, 1, 'player.exe')]
    assert roots(processes, [100, 101, 200, 201, 210, 220, 300, 400]) == [300, 400]


def test_active_parent_and_child_are_captured_once():
    processes = [P(100, 0, 1, 'hdr.exe'), P(300, 0, 1, 'browser.exe'),
                 P(301, 300, 2, 'audio.exe')]
    assert roots(processes, [300, 301]) == [300]


def test_allowed_ancestor_of_discord_is_unsafe():
    processes = [P(100, 0, 1, 'hdr.exe'), P(300, 0, 1, 'launcher.exe'),
                 P(301, 300, 2, 'Discord.exe')]
    with pytest.raises(AudioPolicyError, match='excluded'):
        roots(processes, [300])


def test_unknown_active_pid_fails_closed():
    with pytest.raises(AudioPolicyError, match='Unknown'):
        roots([P(100, 0, 1, 'hdr.exe')], [900])


def test_duplicate_pid_identity_fails_closed():
    with pytest.raises(AudioPolicyError, match='identity'):
        roots([P(100, 0, 1, 'hdr.exe'), P(300, 0, 1, 'game.exe'),
               P(300, 0, 2, 'Discord.exe')], [300])


def test_reused_parent_pid_does_not_exclude_unrelated_older_child():
    processes = [P(100, 0, 1, 'hdr.exe'), P(200, 0, 30, 'Discord.exe'),
                 P(300, 200, 20, 'game.exe')]
    assert roots(processes, [300]) == [300]


def test_missing_own_identity_fails_closed():
    with pytest.raises(AudioPolicyError, match='own'):
        roots([P(300, 0, 1, 'game.exe')], [300])


def test_cycle_fails_closed():
    with pytest.raises(AudioPolicyError, match='cycle'):
        roots([P(100, 0, 1, 'hdr.exe'), P(300, 301, 2, 'game.exe'),
               P(301, 300, 2, 'helper.exe')], [300])
