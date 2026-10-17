import hashlib
import zipfile

import pytest

from hdr_share.devices import PackageError, verify_package


def package(tmp_path):
    archive = tmp_path / 'driver.zip'
    with zipfile.ZipFile(archive, 'w') as out:
        out.writestr('driver.cat', b'catalog')
        out.writestr('driver.dll', b'binary')
    return archive, hashlib.sha256(archive.read_bytes()).hexdigest()


def test_tampered_package_is_rejected(tmp_path):
    archive, digest = package(tmp_path)
    archive.write_bytes(archive.read_bytes() + b'tampered')
    with pytest.raises(PackageError, match='SHA-256'):
        verify_package(archive, digest, {'driver.cat', 'driver.dll'})


def test_missing_package_member_blocks_install(tmp_path):
    archive, digest = package(tmp_path)
    with pytest.raises(PackageError, match='missing'):
        verify_package(archive, digest, {'driver.sys'})


def test_path_traversal_blocks_extraction(tmp_path):
    archive = tmp_path / 'driver.zip'
    with zipfile.ZipFile(archive, 'w') as out:
        out.writestr('../evil.dll', b'x')
    with pytest.raises(PackageError, match='path'):
        verify_package(archive, hashlib.sha256(archive.read_bytes()).hexdigest(), set())


@pytest.mark.parametrize('status,subject', [('NotSigned', ''), ('Valid', 'Untrusted publisher')])
def test_missing_or_untrusted_signature_blocks_install(status, subject):
    from hdr_share.devices import verify_signature
    with pytest.raises(PackageError, match='signature'):
        verify_signature(status, subject, {'SignPath Foundation'})


def test_trusted_signature_is_accepted():
    from hdr_share.devices import verify_signature
    verify_signature('Valid', 'CN=SignPath Foundation, O=SignPath Foundation', {'SignPath Foundation'})


def test_device_check_does_not_report_ready_without_audio_output():
    from hdr_share.devices import check_devices
    class Display:
        def owned_display(self): return 'own'
    class Audio:
        def endpoints(self): return []
    result = check_devices(display_backend=Display(), audio_bridge=Audio())
    assert not result.ready
    assert any('VB-CABLE' in issue for issue in result.issues)
