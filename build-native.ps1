param([switch]$TestsOnly, [switch]$WithProbes)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
    $vs = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if (-not $vs) { throw 'MSVC x64 Build Tools are required to build the native module.' }
    $vcvars = Join-Path $vs 'VC/Auxiliary/Build/vcvars64.bat'
    $out = Join-Path $PSScriptRoot 'build/native'
    New-Item -ItemType Directory -Force -Path $out | Out-Null
    $commands = @('@echo off', ('call "' + $vcvars + '" >nul'), 'if errorlevel 1 exit /b 1',
        ('cl /nologo /EHsc /std:c++17 /W4 /MD /O2 /I "' + $PSScriptRoot + '\native" "' + $PSScriptRoot + '\native\tests\audio_mixer_test.cpp" /Fo:"' + $out + '\mixer_test.obj" /Fe:"' + $out + '\audio_mixer_test.exe"'),
        'if errorlevel 1 exit /b 1', ('"' + $out + '\audio_mixer_test.exe"'), 'if errorlevel 1 exit /b 1')
    if (-not $TestsOnly) {
        $commands += ('cl /nologo /EHsc /std:c++17 /W4 /MD /O2 /LD /DUNICODE /D_UNICODE /I "' + $PSScriptRoot + '\native" "' + $PSScriptRoot + '\native\audio_bridge.cpp" /Fo:"' + $out + '\audio_bridge.obj" /Fe:"' + $out + '\audio_bridge.dll" /link /IMPLIB:"' + $out + '\audio_bridge.lib" ole32.lib mmdevapi.lib uuid.lib propsys.lib advapi32.lib')
        $commands += 'if errorlevel 1 exit /b 1'
        $commands += ('cl /nologo /EHsc /std:c++17 /W4 /MD /O2 /LD /DUNICODE /D_UNICODE /DNOMINMAX "' + $PSScriptRoot + '\native\video_presenter.cpp" /Fo:"' + $out + '\video_presenter.obj" /Fe:"' + $out + '\video_presenter.dll" /link /IMPLIB:"' + $out + '\video_presenter.lib" d3d11.lib dxgi.lib user32.lib')
        $commands += 'if errorlevel 1 exit /b 1'
    }
    if ($WithProbes) {
        $commands += ('cl /nologo /EHsc /std:c++17 /W4 /MD /O2 /DUNICODE /D_UNICODE "' + $PSScriptRoot + '\native\tests\tone.cpp" /Fo:"' + $out + '\tone.obj" /Fe:"' + $out + '\tone.exe" /link ole32.lib uuid.lib')
        $commands += 'if errorlevel 1 exit /b 1'
    }
    $cmdFile = Join-Path $out 'compile.cmd'
    Set-Content -LiteralPath $cmdFile -Value $commands -Encoding Default
    & $env:ComSpec /d /c ('"' + $cmdFile + '"')
    if ($LASTEXITCODE -ne 0) { throw "Native build/test failed: $LASTEXITCODE" }
} finally { Pop-Location }
