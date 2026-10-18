"""Exercise the real PowerShell coordinator without installing devices."""
import json
import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/setup-components.ps1'


def powershell(tmp_path, body):
    probe = tmp_path / 'probe.ps1'
    probe.write_text(
        "$ErrorActionPreference = 'Stop'\n"
        f". '{SCRIPT.as_posix()}' -LibraryOnly\n" + body, encoding='utf-8-sig')
    environment = dict(os.environ, PSModulePath=str(Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/Modules'))
    result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                             '-File', str(probe)], capture_output=True, text=True, env=environment)
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def test_no_selected_drivers_never_probes_or_installs(tmp_path):
    result = powershell(tmp_path, """
function Test-HssComponentInstalled { throw 'Unexpected device probe' }
function Install-HssComponent { throw 'Unexpected driver install' }
ConvertTo-Json -InputObject @(Invoke-HssSelectedComponents -Components @() -Workspace $PSScriptRoot)
""")
    assert result == []


def test_existing_component_is_skipped(tmp_path):
    result = powershell(tmp_path, """
function Test-HssComponentInstalled { return $true }
function Install-HssComponent { throw 'Must not reinstall' }
Invoke-HssSelectedComponents -Components @('vbcable') -Workspace $PSScriptRoot | ConvertTo-Json
""")
    assert result['state'] == 'already-installed'
    assert result['restart'] is False


def test_failure_does_not_install_unselected_components_or_hide_other_results(tmp_path):
    result = powershell(tmp_path, """
function Test-HssComponentInstalled { return $false }
function Install-HssComponent {
    param($Component, $Workspace)
    if ($Component -eq 'vdd') { throw 'Download rejected' }
    if ($Component -ne 'vbcable') { throw 'Unselected component' }
    return $true
}
@(Invoke-HssSelectedComponents -Components @('vdd','vbcable') -Workspace $PSScriptRoot) | ConvertTo-Json
""")
    assert [item['state'] for item in result] == ['failed', 'installed']
    assert result[0]['message'] == 'Download rejected'
    assert result[1]['restart'] is True


def test_archive_tampering_is_rejected_before_extraction(tmp_path):
    result = powershell(tmp_path, """
$archive = Join-Path $PSScriptRoot 'bad.zip'
[IO.File]::WriteAllText($archive, 'tampered')
try {
    Expand-HssVerifiedArchive -Archive $archive -Destination (Join-Path $PSScriptRoot 'extract') -Descriptor @{sha256=('0' * 64); required=@()}
    throw 'Verification incorrectly succeeded'
} catch {
    @{message=$_.Exception.Message; extracted=(Test-Path (Join-Path $PSScriptRoot 'extract'))} | ConvertTo-Json
}
""")
    assert 'SHA-256' in result['message']
    assert result['extracted'] is False


def test_working_vbcable_is_skipped_even_with_an_old_failed_devnode(tmp_path):
    result = powershell(tmp_path, """
function Get-PnpDevice { @(
    [pscustomobject]@{Status='OK'; FriendlyName='VB-Audio Virtual Cable'; InstanceId='good'},
    [pscustomobject]@{Status='Error'; FriendlyName='VB-Audio Virtual Cable'; InstanceId='old'}
) }
function Get-PnpDeviceProperty { [pscustomobject]@{Data=@('VBAudioVACWDM')} }
@{installed=(Test-HssComponentInstalled 'vbcable')} | ConvertTo-Json
""")
    assert result['installed'] is True


def test_forged_signature_publisher_is_rejected(tmp_path):
    result = powershell(tmp_path, """
function Get-AuthenticodeSignature { [pscustomobject]@{
    Status='Valid'; SignerCertificate=[pscustomobject]@{Subject='CN=Fake SignPath Foundation, O=Attacker'}
} }
try { Assert-HssDriverSignature 'test.dll' @('SignPath Foundation'); $accepted=$true } catch { $accepted=$false }
@{accepted=$accepted} | ConvertTo-Json
""")
    assert result['accepted'] is False


@pytest.mark.parametrize('selected,status,code', [('', 'ok', 0), ('unsupported', 'failed', 1)])
def test_helper_persists_machine_readable_completion_status(tmp_path, selected, status, code):
    result = powershell(tmp_path, f"""
$report = Join-Path $PSScriptRoot 'report.txt'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File '{SCRIPT.as_posix()}' -ReportPath $report {('-Selected ' + selected) if selected else ''}
@{{code=$LASTEXITCODE; status=[IO.File]::ReadAllText($report + '.status')}} | ConvertTo-Json
""")
    assert result == {'code': code, 'status': status}


@pytest.mark.parametrize('exit_code,accepted', [(0, True), (3010, True), (1, False), (-1, False)])
def test_driver_exit_codes_are_not_silently_ignored(tmp_path, exit_code, accepted):
    result = powershell(tmp_path, f"""
try {{ Assert-HssInstallerExitCode -Code {exit_code}; $accepted=$true }} catch {{ $accepted=$false }}
@{{accepted=$accepted}} | ConvertTo-Json
""")
    assert result['accepted'] is accepted
