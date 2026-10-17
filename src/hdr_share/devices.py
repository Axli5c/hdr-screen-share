"""Device package checks. Verification never installs or extracts a driver."""
from dataclasses import dataclass
import hashlib
from pathlib import Path, PurePosixPath
import re
import zipfile


class PackageError(RuntimeError):
    pass


@dataclass(frozen=True)
class DeviceCheck:
    ready: bool
    issues: list[str]


def verify_package(path: Path, sha256: str, required: set[str]) -> None:
    with path.open('rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    if actual.casefold() != sha256.casefold():
        raise PackageError('SHA-256 mismatch: ' + path.name)
    with zipfile.ZipFile(path) as archive:
        names = set()
        for entry in archive.infolist():
            name = entry.filename.replace('\\', '/')
            parsed = PurePosixPath(name)
            if parsed.is_absolute() or '..' in parsed.parts or ':' in name:
                raise PackageError('Unsafe archive path: ' + name)
            if name.casefold() in names:
                raise PackageError('Duplicate archive path: ' + name)
            names.add(name.casefold())
        missing = {item for item in required if item.casefold() not in names}
        if missing:
            raise PackageError('Package members missing: ' + ', '.join(sorted(missing)))


def verify_signature(status: str, subject: str, publishers: set[str]) -> None:
    # Compare complete CN/O attributes, never accept a substring of an issuer.
    attributes = {value.strip().casefold() for value in re.findall(
        r'(?:^|,)\s*(?:CN|O)=([^,]+)', subject, flags=re.IGNORECASE)}
    if status != 'Valid' or not attributes.intersection(p.casefold() for p in publishers):
        raise PackageError('Untrusted driver signature')


def check_devices(*, display_backend=None, audio_bridge=None, require_audio=True, require_display=True) -> DeviceCheck:
    from .virtual_display import WindowsDisplayBackend
    from .audio import NativeAudioBridge, AudioError
    issues = []
    if require_display:
        backend = display_backend if display_backend is not None else WindowsDisplayBackend()
        installed = backend.registered() if hasattr(backend, 'registered') else backend.owned_display() is not None
        if not installed:
            issues.append('Virtual display is not installed')
    if not require_audio:
        return DeviceCheck(not issues, issues)
    try:
        bridge = audio_bridge if audio_bridge is not None else NativeAudioBridge()
        cable = [item for item in bridge.endpoints()
                 if 'CABLE Input' in item['name'] and 'VB-Audio' in item['name']]
        if len(cable) != 1:
            issues.append('VB-CABLE is not installed')
        elif cable[0]['default_roles']:
            issues.append('Set your headphones as the default Windows output')
    except AudioError as error:
        issues.append(str(error))
    return DeviceCheck(not issues, issues)
