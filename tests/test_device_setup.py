import hashlib
import io
import zipfile

import pytest

from hdr_share.device_setup import fetch_vdd
from hdr_share.devices import PackageError


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
