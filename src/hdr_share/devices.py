"""Device package checks. Verification never installs or extracts a driver."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import zipfile


class PackageError(RuntimeError):
    pass


@dataclass(frozen=True)
class DeviceCheck:
    ready: bool
    issues: list[str]


@dataclass(frozen=True)
class DependencyStatus:
    component: str
    name: str
    state: str
    detail: str

    @property
    def ready(self):
        return self.state == 'ready'


def dependency_statuses(*, display_backend=None, audio_bridge=None, reports=(), boot_time=0):
    """Probe each dependency independently; installation reports never prove readiness."""
    from .virtual_display import WindowsDisplayBackend
    from .audio import NativeAudioBridge
    result = []
    state, detail = 'ready', 'Ready for Virtual screen (idle adapter may be disabled).'
    try:
        backend = display_backend if display_backend is not None else WindowsDisplayBackend()
        if not backend.registered():
            state, detail = 'missing', 'Install the app-owned display for Virtual screen mode.'
        else:
            problem = backend.problem_code()
            if problem is None:
                state, detail = 'missing', 'Registered display is not present. Install or repair the driver.'
            elif problem not in (0, 22):
                state, detail = ('restart' if problem == 14 else 'error'), f'Device code {problem}. Restart Windows; if it persists, repair the driver.'
    except Exception as error:
        state, detail = 'error', f'Cannot check virtual display: {error}'
    result.append(DependencyStatus('vdd', 'Virtual Display Driver', state, detail))
    state, detail = 'ready', 'Ready for audio in Application window mode.'
    try:
        bridge = audio_bridge if audio_bridge is not None else NativeAudioBridge()
        cables = [item for item in bridge.endpoints()
                  if 'CABLE Input' in item['name'] and 'VB-Audio' in item['name']]
        if not cables:
            inactive = [item for item in bridge.inactive_endpoints()
                        if 'CABLE Input' in item['name'] and 'VB-Audio' in item['name']]
            if inactive:
                state, detail = 'configure', 'VB-CABLE is disabled or disconnected. Enable CABLE Input in Windows sound settings, then check again.'
            else:
                state, detail = 'missing', 'Install VB-CABLE, then restart Windows to enable window audio.'
        elif len(cables) != 1:
            state, detail = 'configure', 'Multiple CABLE Input devices found. Check Windows sound settings.'
        elif cables[0]['default_roles']:
            state, detail = 'configure', 'Set your headphones or speakers as the default Windows output, including communications.'
    except Exception as error:
        state, detail = 'error', f'Cannot check audio: {error}'
    result.append(DependencyStatus('vbcable', 'VB-CABLE', state, detail))
    pending = set()
    for path in reports:
        try:
            report = json.loads(Path(path).read_text(encoding='utf-8-sig'))
            if float(report['created_at']) < boot_time:
                continue
            pending.update(item['component'] for item in report['results']
                           if item.get('restart') is True and item.get('state') == 'installed')
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            continue
    return [DependencyStatus(item.component, item.name, 'restart',
                             'Installation completed. Restart Windows, then check again.')
            if item.component in pending else item for item in result]


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
