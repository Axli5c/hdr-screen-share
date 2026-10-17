$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $pythonExe = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $pythonExe)) {
        throw 'Сначала создайте .venv и установите requirements-dev.txt по README.md.'
    }
    & (Join-Path $PSScriptRoot 'build-native.ps1')
    # Sandbox and desktop processes can have different ACLs on pytest's shared
    # temp/cache directories. Each build gets its own previously nonexistent path.
    $testTemp = Join-Path ([IO.Path]::GetTempPath()) ('HDRScreenShare-tests-' + [guid]::NewGuid())
    & $pythonExe -m pytest -q -p no:cacheprovider --basetemp $testTemp
    if ($LASTEXITCODE -ne 0) { throw 'Тесты не прошли' }
    & $pythonExe -m compileall -q src tools
    if ($LASTEXITCODE -ne 0) { throw 'Ошибка проверки Python' }
    & $pythonExe -m PyInstaller --noconfirm HDRScreenShare.spec
    if ($LASTEXITCODE -ne 0) { throw 'Ошибка сборки PyInstaller' }
    Copy-Item -LiteralPath 'README.md','THIRD_PARTY_NOTICES.md' -Destination 'dist/HDRScreenShare'
    Copy-Item -LiteralPath 'licenses' -Destination 'dist/HDRScreenShare' -Recurse -Force
    New-Item -ItemType Directory -Force -Path 'dist/HDRScreenShare/docs' | Out-Null
    Copy-Item -LiteralPath 'docs/verification.md' -Destination 'dist/HDRScreenShare/docs'
    Copy-Item -LiteralPath 'docs/verification-v2.md' -Destination 'dist/HDRScreenShare/docs'
    Write-Output (Join-Path $PSScriptRoot 'dist/HDRScreenShare/HDRScreenShare.exe')
}
finally { Pop-Location }
