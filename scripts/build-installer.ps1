param([string]$Compiler)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $Compiler) {
    $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($command) { $Compiler = $command.Source }
    else {
        foreach ($candidate in @((Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
                                 (Join-Path $projectRoot '.scratch/inno/compiler/ISCC.exe'))) {
            if (Test-Path -LiteralPath $candidate) { $Compiler = $candidate; break }
        }
    }
}
if (-not $Compiler) { throw 'Install Inno Setup 6.7 or newer, or pass -Compiler <path to ISCC.exe>.' }
$metadata = Get-Content -LiteralPath (Join-Path $projectRoot 'pyproject.toml') -Raw
$version = [regex]::Match($metadata, '(?m)^version\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"').Groups[1].Value
$portable = Join-Path $projectRoot 'dist/HDRScreenShare'
$exe = Join-Path $portable 'HDRScreenShare.exe'
if (-not (Test-Path -LiteralPath $exe)) { throw 'Run build.ps1 first.' }
if ((Get-Item -LiteralPath $exe).VersionInfo.FileVersion -ne $version) { throw 'Executable and source versions differ.' }
foreach ($name in @('README.md','README.ru.md','CHANGELOG.md','LICENSE','THIRD_PARTY_NOTICES.md')) {
    Copy-Item -LiteralPath (Join-Path $projectRoot $name) -Destination $portable
}
Copy-Item -LiteralPath (Join-Path $projectRoot 'licenses/inno-setup-LICENSE.txt') -Destination (Join-Path $portable 'licenses/inno-setup-LICENSE.txt')
Copy-Item -LiteralPath (Join-Path $projectRoot 'docs/verification-installer.md') -Destination (Join-Path $portable 'docs/verification-installer.md')
& $Compiler "/DAppVersion=$version" (Join-Path $PSScriptRoot 'installer.iss')
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup compilation failed.' }
$output = Join-Path $projectRoot "dist/releases/HDRScreenShare-Setup-v$version-windows-x64.exe"
$lines = @(Get-ChildItem -LiteralPath (Join-Path $projectRoot 'dist/releases') -File | Where-Object {
    $_.Name -eq "HDRScreenShare-Setup-v$version-windows-x64.exe" -or $_.Name -eq "HDRScreenShare-v$version-windows-x64.zip"
} | Sort-Object Name | ForEach-Object {
    "$((Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant())  $($_.Name)"
})
[IO.File]::WriteAllText((Join-Path $projectRoot 'dist/releases/SHA256SUMS.txt'), ($lines -join "`n") + "`n", [Text.UTF8Encoding]::new($false))
Write-Output $output
