from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET


def test_config_generation_works_in_windows_powershell_51(tmp_path):
    root = Path(__file__).resolve().parents[1]
    source = tmp_path / 'input.xml'
    output = tmp_path / 'output.xml'
    source.write_text('<vdd_settings><monitors><count>1</count></monitors><global>'
                      '<g_refresh_rate>144</g_refresh_rate></global><resolutions>'
                      '<resolution><width>3840</width><height>2160</height>'
                      '<refresh_rate>30</refresh_rate></resolution></resolutions></vdd_settings>')
    result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command',
        f". '{root / 'scripts/vdd-config.ps1'}'; "
        f"$doc = New-HssVddConfig '{source}'; $doc.Save('{output}')"], capture_output=True)
    assert result.returncode == 0, result.stderr.decode(errors='replace')
    document = ET.parse(output)
    assert [node.text for node in document.findall('./global/g_refresh_rate')] == ['60']
    modes = {(int(node.findtext('width')), int(node.findtext('height')),
              int(node.findtext('refresh_rate'))) for node in document.findall('./resolutions/resolution')}
    assert modes == {(3840, 2160, 60), (2160, 3840, 60)}
