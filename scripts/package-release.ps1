param([string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $projectRoot 'dist/releases' }
$metadata = Get-Content -LiteralPath (Join-Path $projectRoot 'pyproject.toml') -Raw
$versionMatch = [regex]::Match($metadata, '(?m)^version\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"')
if (-not $versionMatch.Success) { throw 'Project version not found' }
$version = $versionMatch.Groups[1].Value
$portable = Join-Path $projectRoot 'dist/HDRScreenShare'
$exe = Join-Path $portable 'HDRScreenShare.exe'
if (-not (Test-Path -LiteralPath $exe)) { throw 'Run build.ps1 first' }
if ((Get-Item -LiteralPath $exe).VersionInfo.FileVersion -ne $version) { throw 'Executable and source versions differ' }
foreach ($name in @('README.md', 'README.ru.md', 'CHANGELOG.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md')) {
    Copy-Item -LiteralPath (Join-Path $projectRoot $name) -Destination $portable
}
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$archive = Join-Path $OutputDirectory "HDRScreenShare-v$version-windows-x64.zip"
Compress-Archive -LiteralPath $portable -DestinationPath $archive -Force
$checksumPath = Join-Path $OutputDirectory 'SHA256SUMS.txt'
$lines = @(Get-ChildItem -LiteralPath $OutputDirectory -File | Where-Object {
    $_.Name -eq "HDRScreenShare-v$version-windows-x64.zip" -or $_.Name -eq "HDRScreenShare-Setup-v$version-windows-x64.exe"
} | Sort-Object Name | ForEach-Object {
    "$((Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant())  $($_.Name)"
})
[IO.File]::WriteAllText($checksumPath, ($lines -join "`n") + "`n", [Text.UTF8Encoding]::new($false))
Write-Output $archive
Write-Output $checksumPath
