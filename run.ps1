$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.venv/Scripts/pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw 'Нет .venv. Используйте собранный exe или создайте окружение по README.md.'
}
$env:PYTHONPATH = Join-Path $projectRoot 'src'
Start-Process -FilePath $pythonExe -ArgumentList @('-m', 'hdr_share') -WorkingDirectory $projectRoot -WindowStyle Hidden
