import hashlib
import io
import zipfile

import pytest

from hdr_share.device_setup import fetch_vdd
from hdr_share.devices import PackageError


def wait_for(app, predicate):
    import time
    end = time.monotonic() + 3
    while not predicate() and time.monotonic() < end:
        app.processEvents()
        time.sleep(.005)
    assert predicate()


def test_dialog_shows_both_components_and_rechecks_after_manual_install(app):
    from hdr_share.device_setup import DeviceSetupDialog
    from hdr_share.devices import DependencyStatus
    snapshot = [DependencyStatus('vdd', 'Virtual Display Driver', 'missing', 'Install display'),
                DependencyStatus('vbcable', 'VB-CABLE', 'ready', 'Window audio ready')]
    box = DeviceSetupDialog(probe=lambda: list(snapshot))
    try:
        wait_for(app, lambda: bool(box.results))
        assert not box.display_button.isHidden() and not box.cable_button.isHidden()
        assert box.display_button.isEnabled() and not box.cable_button.isEnabled()
        assert '✓' in box.rows['vbcable'].text()
        assert '✗' in box.rows['vdd'].text()
        snapshot[0] = DependencyStatus('vdd', 'Virtual Display Driver', 'ready', 'Ready')
        box.check_button.click()
        wait_for(app, lambda: box.results[0].ready)
        assert not box.display_button.isEnabled()
    finally:
        box.close()


def test_cancelled_elevation_is_visible_and_can_be_retried(app, tmp_path):
    from hdr_share.device_setup import DeviceSetupDialog
    from hdr_share.devices import DependencyStatus
    def cancelled(component, report):
        raise OSError(1223, 'Operation cancelled by user')
    box = DeviceSetupDialog(probe=lambda: [
        DependencyStatus('vdd', 'Virtual Display Driver', 'missing', 'Install display')],
        installer_factory=cancelled, report_dir=tmp_path)
    try:
        wait_for(app, lambda: bool(box.results))
        box.display_button.click()
        assert 'cancel' in box.install_status.text().lower()
        assert box.display_button.isEnabled()
        assert not box.results[0].ready
    finally:
        box.close()


def test_install_success_without_report_does_not_claim_ready(app, tmp_path):
    from hdr_share.device_setup import DeviceSetupDialog
    from hdr_share.devices import DependencyStatus
    class Installer:
        def poll(self): return 0
    box = DeviceSetupDialog(probe=lambda: [
        DependencyStatus('vdd', 'Virtual Display Driver', 'missing', 'Install display')],
        installer_factory=lambda component, report: Installer(), report_dir=tmp_path)
    try:
        wait_for(app, lambda: bool(box.results))
        box.display_button.click()
        assert not box.check_button.isEnabled()
        assert not box.close()
        box.poll_install()
        wait_for(app, lambda: box.check_button.isEnabled())
        assert 'report' in box.install_status.text().lower()
        assert not box.results[0].ready
    finally:
        box.close()


def test_driver_download_rejects_bad_bytes_without_replacing_cache(tmp_path):
    destination = tmp_path / 'driver.zip'
    destination.write_bytes(b'existing-cache')
    descriptor = {'url': 'https://example.invalid/driver.zip', 'sha256': '0' * 64, 'required': []}
    with pytest.raises(PackageError):
        fetch_vdd(destination, descriptor, opener=lambda url: io.BytesIO(b'tampered'))
    assert destination.read_bytes() == b'existing-cache'


def test_verified_driver_download_is_ready_for_installer(tmp_path):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        archive.writestr('driver.cat', b'catalog')
    content = stream.getvalue()
    descriptor = {'url': 'https://example.invalid/driver.zip',
                  'sha256': hashlib.sha256(content).hexdigest(), 'required': ['driver.cat']}
    destination = tmp_path / 'driver.zip'
    assert fetch_vdd(destination, descriptor, opener=lambda url: io.BytesIO(content)) == destination
    assert destination.read_bytes() == content
