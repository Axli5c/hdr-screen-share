param(
    [Parameter(Mandatory=$true)][string]$VddArchive,
    [switch]$VerifyOnly,
    [switch]$ResumePreparation
)
$ErrorActionPreference = 'Stop'
$installLog = $null
if (-not $VerifyOnly) {
    $logDirectory = Join-Path $env:LOCALAPPDATA 'HDRScreenShare'
    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
    $installLog = Join-Path $logDirectory 'device-install.log'
    Start-Transcript -LiteralPath $installLog -Append | Out-Null
}
# This helper installs only the dedicated display. VB-CABLE remains an independent
# original vendor installation; its package is not integrated into our installer.
$expected = 'F93E7CE3D640C83C419B1B72D2C83B2D8E34D83E8B7BA11F3328A40D2DA82FA4'
$archive = (Resolve-Path -LiteralPath $VddArchive).Path
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $expected) {
    throw 'VDD archive SHA-256 mismatch. Nothing installed.'
}
$stage = Join-Path ([IO.Path]::GetTempPath()) ('HDRScreenShare-verify-' + [guid]::NewGuid())
[IO.Directory]::CreateDirectory($stage) | Out-Null
try {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($archive)
    try {
        foreach ($entry in $zip.Entries) {
            $name = $entry.FullName.Replace('\','/')
            if ($name.StartsWith('/') -or $name.Contains(':') -or ($name.Split('/') -contains '..')) {
                throw 'Unsafe archive path'
            }
        }
        foreach ($name in @('MttVDD.inf','mttvdd.cat','MttVDD.dll','vdd_settings.xml')) {
            $entries = @($zip.Entries | Where-Object { $_.FullName -ieq $name })
            if ($entries.Count -ne 1) { throw "Missing or duplicate archive member: $name" }
            [IO.Compression.ZipFileExtensions]::ExtractToFile($entries[0], (Join-Path $stage $name))
        }
    } finally { $zip.Dispose() }
    foreach ($name in @('mttvdd.cat','MttVDD.dll')) {
        $signature = Get-AuthenticodeSignature -LiteralPath (Join-Path $stage $name)
        if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch '(?:^|,\s*)CN=SignPath Foundation(?:,|$)') {
            throw "Untrusted VDD signature: $name"
        }
    }
    $inf = Get-Content -LiteralPath (Join-Path $stage 'MttVDD.inf') -Raw
    if ($inf -notmatch '(?im)^CatalogFile\s*=\s*MttVDD\.cat\s*$' -or $inf -notmatch 'Root\\MttVDD') {
        throw 'Unexpected signed INF hardware identity or catalog'
    }
    . (Join-Path $PSScriptRoot 'vdd-config.ps1')
    $configuration = New-HssVddConfig (Join-Path $stage 'vdd_settings.xml')
    if ($VerifyOnly) {
        Write-Output 'Verified pinned archive, INF, SignPath catalog and DLL. Nothing installed.'
        return
    }
    $principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Run this installer as Administrator. The application itself needs no elevation.'
    }
    $vendorKey = 'HKLM:\SOFTWARE\MikeTheTech\VirtualDisplayDriver'
    $ownerKey = 'HKLM:\SOFTWARE\HDRScreenShare'
    $destination = Join-Path $env:ProgramData 'HDRScreenShare\Devices\VDD-24.12.24'
    $existing = @(Get-PnpDevice -Class Display | Where-Object {
        $_.InstanceId -match '^ROOT\\(MTTVDD|HDRSCREENSHAREVDD)\\' -or $_.FriendlyName -match 'MttVDD|Virtual Display'
    })
    $resumeSafe = $false
    if ($ResumePreparation -and -not $existing.Count) {
        $vendor = Get-ItemProperty -LiteralPath $vendorKey -ErrorAction SilentlyContinue
        $owner = Get-ItemProperty -LiteralPath $ownerKey -ErrorAction SilentlyContinue
        $resumeSafe = $vendor.VDDPATH -eq $destination -and
            (-not $owner.DeviceInstance -or $owner.DeviceInstance -eq 'ROOT\HDRSCREENSHAREVDD\0000') -and
            (-not $owner.PackageHash -or $owner.PackageHash -eq $expected)
    }
    if ($existing.Count -or (((Test-Path $vendorKey) -or (Test-Path $ownerKey)) -and -not $resumeSafe)) {
        throw 'Existing VDD/device ownership found. Refusing to claim or overwrite it.'
    }
    $configuration.Save((Join-Path $stage 'vdd_settings.xml'))
    if (Test-Path -LiteralPath $destination) {
        # Resume only the exact three authenticated files left before registration.
        foreach ($file in Get-ChildItem -LiteralPath $destination -Force) {
            if ($file.PSIsContainer -or $file.Name -notin @('MttVDD.inf','mttvdd.cat','MttVDD.dll','vdd_settings.xml') -or
                (Get-FileHash -LiteralPath $file.FullName).Hash -ne (Get-FileHash -LiteralPath (Join-Path $stage $file.Name)).Hash) {
                throw 'Existing device directory has unknown contents; manual inspection required.'
            }
        }
    } else { New-Item -ItemType Directory -Path $destination | Out-Null }
    Copy-Item -LiteralPath (Join-Path $stage 'MttVDD.inf'),(Join-Path $stage 'mttvdd.cat'),(Join-Path $stage 'MttVDD.dll') -Destination $destination
    # Configuration is outside the signed package. Keep the only supported rate 60 Hz.
    $configuration.Save((Join-Path $destination 'vdd_settings.xml'))

    Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
public static class HssDeviceSetup {
    [StructLayout(LayoutKind.Sequential)] public struct DeviceInfo {
        public uint Size; public Guid ClassGuid; public uint DevInst; public UIntPtr Reserved;
    }
    [DllImport("setupapi.dll", SetLastError=true)] static extern IntPtr SetupDiCreateDeviceInfoList(ref Guid g, IntPtr hwnd);
    [DllImport("setupapi.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern bool SetupDiCreateDeviceInfoW(IntPtr set, string name, ref Guid g, string description, IntPtr hwnd, uint flags, ref DeviceInfo info);
    [DllImport("setupapi.dll", SetLastError=true)] static extern bool SetupDiSetDeviceRegistryPropertyW(IntPtr set, ref DeviceInfo info, uint property, byte[] buffer, uint size);
    [DllImport("setupapi.dll", SetLastError=true)] static extern bool SetupDiCallClassInstaller(uint function, IntPtr set, ref DeviceInfo info);
    [DllImport("setupapi.dll", SetLastError=true)] static extern bool SetupDiDestroyDeviceInfoList(IntPtr set);
    public static void Register() {
        Guid g = new Guid("4D36E968-E325-11CE-BFC1-08002BE10318");
        IntPtr set = SetupDiCreateDeviceInfoList(ref g, IntPtr.Zero);
        if (set == new IntPtr(-1)) throw new Win32Exception();
        try {
            DeviceInfo info = new DeviceInfo(); info.Size = (uint)Marshal.SizeOf(info);
            if (!SetupDiCreateDeviceInfoW(set, @"ROOT\HDRSCREENSHAREVDD\0000", ref g, "HDR Screen Share Virtual Display", IntPtr.Zero, 0, ref info)) throw new Win32Exception();
            byte[] ids = System.Text.Encoding.Unicode.GetBytes("Root\\MttVDD\0\0");
            if (!SetupDiSetDeviceRegistryPropertyW(set, ref info, 1, ids, (uint)ids.Length)) throw new Win32Exception();
            if (!SetupDiCallClassInstaller(0x19, set, ref info)) throw new Win32Exception();
        } finally { SetupDiDestroyDeviceInfoList(set); }
    }
}
'@
    # Once the root devnode is registered, failures leave a visible exact identity
    # for diagnosis; never remove a device chosen by a friendly-name wildcard.
    $vendorRegistry = [Microsoft.Win32.Registry]::LocalMachine.CreateSubKey('SOFTWARE\MikeTheTech\VirtualDisplayDriver')
    try { $vendorRegistry.SetValue('VDDPATH', $destination, [Microsoft.Win32.RegistryValueKind]::String) }
    finally { $vendorRegistry.Dispose() }
    $ownerRegistry = [Microsoft.Win32.Registry]::LocalMachine.CreateSubKey('SOFTWARE\HDRScreenShare')
    try {
        $ownerRegistry.SetValue('DeviceInstance', 'ROOT\HDRSCREENSHAREVDD\0000', [Microsoft.Win32.RegistryValueKind]::String)
        $ownerRegistry.SetValue('PackageHash', $expected, [Microsoft.Win32.RegistryValueKind]::String)
    } finally { $ownerRegistry.Dispose() }
    [HssDeviceSetup]::Register()
    & "$env:SystemRoot\System32\pnputil.exe" /add-driver (Join-Path $destination 'MttVDD.inf') /install
    if ($LASTEXITCODE -notin @(0,3010)) { throw "pnputil failed: $LASTEXITCODE. Preserve device for diagnosis." }
    & "$env:SystemRoot\System32\pnputil.exe" /disable-device 'ROOT\HDRSCREENSHAREVDD\0000'
    if ($LASTEXITCODE -ne 0) { throw "Cannot disable idle adapter: $LASTEXITCODE" }
    Write-Output 'Dedicated signed VDD installed and disabled until Start. No automatic reboot.'
} catch {
    $_ | Out-String | Write-Output
    throw
} finally {
    # The target is the GUID directory created above, never a user supplied path.
    if ($stage -and $stage.StartsWith([IO.Path]::GetTempPath(), [StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $stage -Recurse -Force
    }
    if ($installLog) { Stop-Transcript | Out-Null }
}
