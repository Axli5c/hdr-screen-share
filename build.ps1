$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $pythonExe = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $pythonExe)) {
        throw 'Сначала создайте .venv и установите requirements-dev.txt по README.md.'
    }
    & $pythonExe -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Тесты не прошли' }
    & $pythonExe -m PyInstaller --noconfirm HDRScreenShare.spec
    if ($LASTEXITCODE -ne 0) { throw 'Ошибка сборки PyInstaller' }
    Copy-Item -LiteralPath 'README.md','THIRD_PARTY_NOTICES.md' -Destination 'dist/HDRScreenShare'
    Copy-Item -LiteralPath 'licenses' -Destination 'dist/HDRScreenShare' -Recurse -Force
    New-Item -ItemType Directory -Force -Path 'dist/HDRScreenShare/docs' | Out-Null
    Copy-Item -LiteralPath 'docs/verification.md' -Destination 'dist/HDRScreenShare/docs'
    Write-Output (Join-Path $PSScriptRoot 'dist/HDRScreenShare/HDRScreenShare.exe')
}
finally { Pop-Location }
