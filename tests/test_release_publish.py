import hashlib
from pathlib import Path

import pytest

from tools.publish_release import publish


def test_draft_release_is_resolved_by_id_instead_of_published_tag_endpoint(monkeypatch):
    from tools.publish_release import GitHub
    def api(*args, **kwargs):
        if args == ('release', 'view', 'v0.2.5', '--repo', 'owner/repo', '--json', 'databaseId'):
            return {'databaseId': 42}
        if args == ('api', 'repos/owner/repo/releases/42'):
            return {'draft': True, 'assets': [{'id': 7, 'state': 'uploaded'}]}
        raise RuntimeError('Not Found (HTTP 404): draft unavailable by tag')
    github = GitHub()
    monkeypatch.setattr(github, 'call', api)
    assert github.release('owner/repo', 'v0.2.5')['assets'] == [{'id': 7, 'state': 'uploaded'}]


class FakeGitHub:
    def __init__(self, fail_upload=None, corrupt=False, fail_promotion=False):
        self.assets = []
        self.events = []
        self.fail_upload = fail_upload
        self.corrupt = corrupt
        self.fail_promotion = fail_promotion

    def release(self, repo, tag):
        return {'assets': [dict(asset) for asset in self.assets]}

    def upload(self, repo, tag, path):
        self.events.append(('upload', path.name))
        if len([event for event in self.events if event[0] == 'upload']) == self.fail_upload:
            raise RuntimeError('Upload interrupted')
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assets.append({'id': len(self.assets) + 100, 'name': path.name,
                            'state': 'uploaded', 'digest': 'sha256:' + ('0' * 64 if self.corrupt else digest)})

    def delete(self, repo, asset_id):
        asset = next(asset for asset in self.assets if asset['id'] == asset_id)
        self.events.append(('delete', asset['name']))
        self.assets.remove(asset)

    def rename(self, repo, asset_id, name):
        self.events.append(('rename', name))
        asset = next(asset for asset in self.assets if asset['id'] == asset_id)
        if self.fail_promotion and asset['digest'] != 'sha256:old' and '.pending-' not in name:
            self.fail_promotion = False
            raise RuntimeError('Promotion interrupted')
        asset['name'] = name


@pytest.fixture
def artifacts(tmp_path):
    names = ['HDRScreenShare-Setup-v0.2.4-windows-x64.exe', 'HDRScreenShare-v0.2.4-windows-x64.zip']
    for name in names:
        (tmp_path / name).write_bytes(name.encode())
    (tmp_path / 'SHA256SUMS.txt').write_text(''.join(
        hashlib.sha256((tmp_path / name).read_bytes()).hexdigest() + '  ' + name + '\n'
        for name in names), encoding='utf-8')
    return tmp_path


def existing_release(github, directory):
    github.assets = [{'id': number, 'name': path.name, 'state': 'uploaded', 'digest': 'sha256:old'}
                     for number, path in enumerate(sorted(directory.iterdir()), 1)]


@pytest.mark.parametrize('failure', ['interrupted', 'corrupt'])
def test_failed_upload_or_verification_preserves_existing_files(artifacts, failure):
    github = FakeGitHub(fail_upload=2 if failure == 'interrupted' else None, corrupt=failure == 'corrupt')
    existing_release(github, artifacts)
    original_names = {asset['name'] for asset in github.assets}
    with pytest.raises(RuntimeError):
        publish(artifacts, 'v0.2.4', 'owner/repo', github)
    assert {asset['name'] for asset in github.assets if asset['digest'] == 'sha256:old'} == original_names
    assert not any(event[0] == 'delete' and event[1] in original_names for event in github.events)


def test_all_new_files_are_verified_before_replacing_any_existing_file(artifacts):
    github = FakeGitHub()
    existing_release(github, artifacts)
    publish(artifacts, 'v0.2.4', 'owner/repo', github)
    assert len(github.assets) == 3
    assert {asset['name'] for asset in github.assets} == {path.name for path in artifacts.iterdir()}
    upload_positions = [index for index, event in enumerate(github.events) if event[0] == 'upload']
    delete_positions = [index for index, event in enumerate(github.events) if event[0] == 'delete']
    assert max(upload_positions) < min(delete_positions)


def test_bad_local_checksum_does_not_touch_github(artifacts):
    (artifacts / 'SHA256SUMS.txt').write_text('invalid')
    github = FakeGitHub()
    with pytest.raises(ValueError):
        publish(artifacts, 'v0.2.4', 'owner/repo', github)
    assert github.events == []


def test_failed_promotion_restores_existing_download_names_and_bytes(artifacts):
    github = FakeGitHub(fail_promotion=True)
    existing_release(github, artifacts)
    original_names = {asset['name'] for asset in github.assets}
    with pytest.raises(RuntimeError):
        publish(artifacts, 'v0.2.4', 'owner/repo', github)
    assert {asset['name'] for asset in github.assets if asset['digest'] == 'sha256:old'} == original_names
    assert not any(event[0] == 'delete' and event[1] in original_names for event in github.events)
