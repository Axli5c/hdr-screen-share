param(
    [string]$Selected = '',
    [string]$ReportPath,
    [ValidateSet('en','ru')][string]$Language = 'en',
    [switch]$LibraryOnly
)
$ErrorActionPreference = 'Stop'
# Windows PowerShell can inherit PowerShell 7's module path when Setup is
# launched from a terminal. Prefer its matching inbox modules.
$env:PSModulePath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\Modules;" + $env:PSModulePath

function Assert-HssInstallerExitCode {
    param([int]$Code)
    if ($Code -notin @(0, 3010)) { throw "Driver installer failed (exit code $Code)." }
}

function Test-HssComponentInstalled {
    param([ValidateSet('vdd','vbcable')][string]$Component)
    if ($Component -eq 'vdd') {
        $owner = Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\HDRScreenShare' -ErrorAction SilentlyContinue
        $device = @(Get-PnpDevice -Class Display -PresentOnly | Where-Object { $_.InstanceId -eq 'ROOT\HDRSCREENSHAREVDD\0000' })
        if (-not $device.Count) { return $false }
        if ($owner.DeviceInstance -ne 'ROOT\HDRSCREENSHAREVDD\0000' -or
            $owner.PackageHash -ne 'F93E7CE3D640C83C419B1B72D2C83B2D8E34D83E8B7BA11F3328A40D2DA82FA4') {
            throw 'Existing virtual display belongs to another installation.'
        }
        $problem = (Get-PnpDeviceProperty -InstanceId $device[0].InstanceId -KeyName 'DEVPKEY_Device_ProblemCode').Data
        if ($problem -notin @(0,22)) { throw "Existing virtual display needs repair (device code $problem)." }
        return $true
    }
    $devices = @(Get-PnpDevice -Class Media -PresentOnly | Where-Object {
        $_.FriendlyName -eq 'VB-Audio Virtual Cable'
    })
    if (-not $devices.Count) { return $false }
    $healthy = @($devices | Where-Object {
        $_.Status -eq 'OK' -and 'VBAudioVACWDM' -in (Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName 'DEVPKEY_Device_HardwareIds').Data
    })
    if (-not $healthy.Count) {
        throw 'Existing VB-CABLE needs repair. Restart Windows or use the original VB-Audio installer.'
    }
    return $true
}

function Save-HssDriverArchive {
    param($Descriptor, [string]$Destination)
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $request = [Net.WebRequest]::Create($Descriptor.url)
    $request.Timeout = 30000
    $request.ReadWriteTimeout = 30000
    $response = $request.GetResponse()
    try {
        $inputStream = $response.GetResponseStream()
        $outputStream = [IO.File]::Create($Destination)
        try {
            $buffer = New-Object byte[] 65536
            $total = 0
            while (($count = $inputStream.Read($buffer, 0, $buffer.Length)) -gt 0) {
                $total += $count
                if ($total -gt 32MB) { throw 'Unexpected driver download size.' }
                $outputStream.Write($buffer, 0, $count)
            }
        } finally { $outputStream.Dispose(); $inputStream.Dispose() }
    } finally { $response.Dispose() }
}

function Expand-HssVerifiedArchive {
    param([string]$Archive, [string]$Destination, $Descriptor)
    if ((Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash -ne $Descriptor.sha256) {
        throw 'Driver archive SHA-256 mismatch. Nothing installed.'
    }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($Archive)
    try {
        $names = @{}
        foreach ($entry in $zip.Entries) {
            $name = $entry.FullName.Replace('\','/')
            if ($name.StartsWith('/') -or $name.Contains(':') -or ($name.Split('/') -contains '..') -or $names.ContainsKey($name)) {
                throw 'Unsafe or duplicate driver archive path.'
            }
            $names[$name] = $true
        }
        foreach ($name in $Descriptor.required) {
            if (-not $names.ContainsKey($name)) { throw "Missing driver archive member: $name" }
        }
    } finally { $zip.Dispose() }
    [IO.Compression.ZipFile]::ExtractToDirectory($Archive, $Destination)
}

function Assert-HssDriverSignature {
    param([string]$Path, [string[]]$Publishers)
    $signature = Get-AuthenticodeSignature -LiteralPath $Path
    $names = @([regex]::Matches($signature.SignerCertificate.Subject, '(?:^|,)\s*(?:CN|O)=([^,]+)') | ForEach-Object { $_.Groups[1].Value.Trim() })
    if ($signature.Status -ne 'Valid' -or -not @($names | Where-Object { $_ -in $Publishers }).Count) {
        throw "Untrusted driver signature: $([IO.Path]::GetFileName($Path))"
    }
}

function Install-HssComponent {
    param([ValidateSet('vdd','vbcable')][string]$Component, [string]$Workspace)
    $descriptor = (Get-Content -LiteralPath (Join-Path $PSScriptRoot 'device-packages.json') -Raw | ConvertFrom-Json).$Component
    $archive = Join-Path $Workspace ($Component + '.zip')
    $extract = Join-Path $Workspace $Component
    Save-HssDriverArchive -Descriptor $descriptor -Destination $archive
    Expand-HssVerifiedArchive -Archive $archive -Destination $extract -Descriptor $descriptor
    if ($Component -eq 'vdd') {
        foreach ($name in @('mttvdd.cat','MttVDD.dll')) {
            Assert-HssDriverSignature -Path (Join-Path $extract $name) -Publishers $descriptor.publishers
        }
        & "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'install-devices.ps1') -VddArchive $archive -ResumePreparation | Out-Host
        $code = $LASTEXITCODE
        Assert-HssInstallerExitCode -Code $code
        if (-not (Test-HssComponentInstalled 'vdd')) { throw 'Virtual display was not registered.' }
        return ($code -eq 3010)
    }
    foreach ($name in @('VBCABLE_Setup_x64.exe','vbaudio_cable64_win10.cat')) {
        Assert-HssDriverSignature -Path (Join-Path $extract $name) -Publishers $descriptor.publishers
    }
    # Original vendor installer; do not import certificates or modify audio defaults.
    $process = Start-Process -FilePath (Join-Path $extract 'VBCABLE_Setup_x64.exe') -ArgumentList '-i','-h' -WorkingDirectory $extract -WindowStyle Hidden -PassThru -Wait
    Assert-HssInstallerExitCode -Code $process.ExitCode
    # VB-Audio requires a restart after installation, including exit code zero.
    return $true
}

function Invoke-HssSelectedComponents {
    param([string[]]$Components, [string]$Workspace)
    foreach ($component in $Components | Select-Object -Unique) {
        $result = [ordered]@{component=$component; state='failed'; restart=$false; message=''}
        try {
            if ($component -notin @('vdd','vbcable')) { throw 'Unknown setup component.' }
            if (Test-HssComponentInstalled $component) {
                $result.state = 'already-installed'
            } else {
                $result.restart = [bool](Install-HssComponent -Component $component -Workspace $Workspace)
                $result.state = 'installed'
            }
        } catch { $result.message = $_.Exception.Message }
        [pscustomobject]$result
    }
}

if ($LibraryOnly) { return }
if (-not $ReportPath) { throw 'ReportPath is required.' }
$workspace = Join-Path ([IO.Path]::GetTempPath()) ('HDRScreenShare-setup-' + [guid]::NewGuid())
[IO.Directory]::CreateDirectory($workspace) | Out-Null
try {
    $results = @(Invoke-HssSelectedComponents -Components @($Selected.Split(',') | Where-Object { $_ }) -Workspace $workspace)
} finally {
    $resolved = [IO.Path]::GetFullPath($workspace)
    $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
    if ($resolved.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase) -and
        [IO.Path]::GetFileName($resolved) -match '^HDRScreenShare-setup-[0-9a-f-]{36}$') {
        Remove-Item -LiteralPath $resolved -Recurse -Force -ErrorAction SilentlyContinue
    }
}
$russian = $Language -eq 'ru'
$lines = @(if ($russian) { 'HDR Screen Share установлен.' } else { 'HDR Screen Share installed.' })
foreach ($result in $results) {
    $name = if ($result.component -eq 'vdd') {
        if ($russian) { 'Драйвер виртуального дисплея' } else { 'Virtual Display Driver' }
    } else { 'VB-CABLE' }
    $state = $result.state
    if ($russian) {
        $state = switch ($state) {
            'installed' { 'установлен' }
            'already-installed' { 'уже установлен' }
            default { 'ошибка установки' }
        }
    }
    $lines += "$name`: $state. $($result.message)".Trim()
}
if (@($results | Where-Object restart).Count) {
    if ($russian) {
        $lines += 'Перезагрузите Windows перед использованием нового драйвера.'
        $lines += 'Оставьте наушники выводом по умолчанию, а микрофон — входом по умолчанию.'
    } else {
        $lines += 'Restart Windows before using the new driver.'
        $lines += 'Keep your headphones as the default output and your microphone as the default input.'
    }
}
[IO.File]::WriteAllText($ReportPath, ($lines -join "`r`n"), [Text.UTF8Encoding]::new($false))
$failed = @($results | Where-Object { $_.state -eq 'failed' }).Count -gt 0
$status = if ($failed) { 'failed' } else { 'ok' }
[IO.File]::WriteAllText(($ReportPath + '.status'), $status, [Text.UTF8Encoding]::new($false))
if ($failed) { exit 1 }
exit 0
