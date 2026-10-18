"""Publish verified release assets without deleting working files before upload."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import uuid


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class GitHub:
    def call(self, *arguments, payload=None):
        try:
            result = subprocess.run(['gh', *arguments],
                                    input=None if payload is None else json.dumps(payload).encode(),
                                    capture_output=True, check=True)
        except subprocess.CalledProcessError as error:
            raise RuntimeError(error.stderr.decode('utf-8', errors='replace').strip()) from error
        return json.loads(result.stdout) if result.stdout.strip() else None

    def release(self, repo, tag):
        # REST's tag endpoint only resolves published releases. gh can also find
        # drafts, whose numeric ID works with the asset verification API.
        release = self.call('release', 'view', tag, '--repo', repo, '--json', 'databaseId')
        return self.call('api', f"repos/{repo}/releases/{release['databaseId']}")

    def upload(self, repo, tag, path):
        self.call('release', 'upload', tag, str(path), '--repo', repo)

    def delete(self, repo, asset_id):
        self.call('api', '--method', 'DELETE', f'repos/{repo}/releases/assets/{asset_id}')

    def rename(self, repo, asset_id, name):
        self.call('api', '--method', 'PATCH', f'repos/{repo}/releases/assets/{asset_id}',
                  '--input', '-', payload={'name': name, 'label': ''})


def publish(directory, tag, repo, github):
    directory = Path(directory)
    if not re.fullmatch(r'v\d+\.\d+\.\d+', tag):
        raise ValueError('Expected a vMAJOR.MINOR.PATCH tag')
    names = [f'HDRScreenShare-Setup-{tag}-windows-x64.exe',
             f'HDRScreenShare-{tag}-windows-x64.zip', 'SHA256SUMS.txt']
    expected = {name: 'sha256:' + sha256(directory / name) for name in names}
    try:
        checksums = dict((name, digest) for digest, name in
                         (line.split('  ', 1) for line in (directory / names[2]).read_text(encoding='utf-8').splitlines()))
    except (ValueError, UnicodeError) as error:
        raise ValueError('Invalid checksum file') from error
    if set(checksums) != set(names[:2]) or any('sha256:' + checksums[name] != expected[name] for name in names[:2]):
        raise ValueError('Release checksums do not match the binaries')
    run_id = uuid.uuid4().hex
    staged_names = {name: name + '.pending-' + run_id for name in names}
    # Temporary names prevent an interrupted upload from removing working assets.
    with tempfile.TemporaryDirectory(prefix='hss-release-') as temporary:
        for name in names:
            path = Path(temporary) / staged_names[name]
            shutil.copyfile(directory / name, path)
            github.upload(repo, tag, path)
        assets = github.release(repo, tag)['assets']
        staged = {}
        for name, candidate in staged_names.items():
            matches = [asset for asset in assets if asset['name'] == candidate]
            if len(matches) != 1 or matches[0]['state'] != 'uploaded' or matches[0].get('digest') != expected[name]:
                raise RuntimeError('Uploaded asset verification failed: ' + name)
            staged[name] = matches[0]
        # Keep old bytes under backup names until all canonical names are verified.
        backups, promoted = [], []
        try:
            for name in names:
                existing = [asset for asset in assets if asset['name'] == name]
                for asset in existing:
                    github.rename(repo, asset['id'], name + '.previous-' + run_id)
                    backups.append((asset['id'], name))
                github.rename(repo, staged[name]['id'], name)
                promoted.append(name)
            assets = github.release(repo, tag)['assets']
            for name in names:
                matches = [asset for asset in assets if asset['name'] == name]
                if len(matches) != 1 or matches[0]['state'] != 'uploaded' or matches[0].get('digest') != expected[name]:
                    raise RuntimeError('Published asset verification failed: ' + name)
        except Exception:
            for name in reversed(promoted):
                try:
                    github.rename(repo, staged[name]['id'], staged_names[name])
                except Exception:
                    pass  # Old bytes remain available under their backup name.
            for asset_id, name in reversed(backups):
                try:
                    github.rename(repo, asset_id, name)
                except Exception:
                    pass  # Preserve backups if GitHub is unavailable during rollback.
            raise
        for asset_id, name in backups:
            github.delete(repo, asset_id)
        for name in names:
            print(name + ': uploaded and SHA-256 verified', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path, default=Path('dist/releases'))
    parser.add_argument('--tag', required=True)
    parser.add_argument('--repo', required=True)
    args = parser.parse_args()
    publish(args.directory, args.tag, args.repo, GitHub())
