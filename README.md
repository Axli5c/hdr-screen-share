# HDR Screen Share 0.2.4

Convert an HDR monitor to SDR for Discord while keeping local HDR enabled.

Windows x64 · Python + Direct3D/WASAPI · MIT · Preview

[Download](https://github.com/Axli5c/hdr-screen-share/releases/tag/v0.2.4) · [Changelog](CHANGELOG.md) · [Release notes](docs/releases/v0.2.4.md) · [License](LICENSE)

## Download

Open [Releases](https://github.com/Axli5c/hdr-screen-share/releases/tag/v0.2.4), choose **v0.2.4**, and download
`HDRScreenShare-v0.2.4-windows-x64.zip`. Extract the entire archive and run
`HDRScreenShare/HDRScreenShare.exe`. Keep `_internal` beside the executable.
Python is not needed for the portable build. This is a portable folder, not an installer.

Use `SHA256SUMS.txt` from the same release to verify the ZIP:

```powershell
Get-FileHash .\HDRScreenShare-v0.2.4-windows-x64.zip -Algorithm SHA256
```

## Requirements

- Windows 11 x64 is the tested platform.
- An HDR-enabled source monitor and desktop Discord.
- Application-window audio: VB-CABLE, installed separately through its original vendor installer.
- Virtual screen mode: the signed virtual display driver installed through **Devices**.

## Quick start

1. Open `HDRScreenShare.exe`. Processing stays off until **Start**.
2. Choose your monitor and sharing mode.
3. Click **Start**. Virtual screen mode asks for Windows UAC to enable its display for this session.
4. Select the source shown by the app in Discord and enable its audio toggle.

**Virtual screen** (default): share the processed SDR screen with Discord system audio. VB-CABLE is not needed for this mode.

**Application window**: share **HDR Screen Share** with application audio. This mode renders a separate SDR window through Direct3D outside the visible desktop, without enabling a virtual monitor or requesting UAC. A virtual display driver is not required. This mode uses the existing VB-CABLE relay to mix application/game audio while excluding desktop Discord and this app. Physical microphone devices are not opened.

| Mode | Discord source | Display/UAC | Audio |
| --- | --- | --- | --- |
| Application window | HDR Screen Share | No virtual monitor or UAC | Filtered application mix via VB-CABLE |
| Virtual screen | Screen number shown by the app | Virtual display; UAC at Start | Discord system audio |

The app opens idle. Video, Audio and Display show separate statuses. Enable **Before / After** for two small previews: the source without tone mapping and the processed SDR output. The Before preview clips raw scRGB to SDR for display; it is an illustration of unmapped highlights, not a reproduction of Discord's private capture pipeline. The raw preview is sampled at up to5FPS, starts only when enabled and pauses while the app is minimized. Comparison failures do not stop the SDR stream.

The control window can be minimized. In Virtual screen mode, full-size output stays on the app-owned virtual display. Stop/close completely disables that dedicated adapter, removing the monitor from Windows display enumeration. A temporary UAC-approved helper also disables it after the main app process crashes. The driver package remains installed for the next screen-mode Start; no permanent service is installed. Physical screens are not duplicated or reconfigured.

## One-time setup

Open **Devices**. Virtual screen mode needs the signed virtual display driver installed once and requests UAC at each Start. Application-window audio needs the original [VB-CABLE installer](https://vb-audio.com/Cable/), linked only in that mode. Keep your headphones as Windows' default output. Application window mode, control window, video and audio run without elevation. Setup and normal use do not reboot automatically.

## Details

Video supports output up to 3840×2160 (portrait 2160×3840), without upscaling, with a 60 FPS target. Preview is 480×270 at up to 15 FPS. Frame counters measure local capture/painting, not Discord viewer FPS.

Discord controls system audio and screen captions in Virtual screen mode. The application's Discord exclusion filter applies only to Application window mode. System/unsupported audio sessions are excluded from the application relay. Browser Discord tabs cannot be isolated from other browser audio; use desktop Discord for filtered sharing.

This is a preview release. End-to-end Discord picker/viewer delivery, audio/video drift and HDR 4K60 have not yet been validated. A changing synthetic 4K window and local 2560×1440 HDR captures were checked; these checks do not establish 4K60 streaming performance.

Validation records: [v0.2.4](docs/verification-v024.md), [v0.2.3](docs/verification-v023.md), [v0.2.1](docs/verification-v021.md), [v0.2.0](docs/verification-v2.md). Ordinary use does not save frames or audio. App log: `%LOCALAPPDATA%/HDRScreenShare/app.log`.

## Build

CPython 3.12 x64, MSVC x64 Build Tools (Desktop development with C++) and the Windows SDK are required for development only. Dependencies are pinned in `requirements.txt` and `requirements-dev.txt`.

```powershell
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
./build.ps1
```

The executable is written to `dist/HDRScreenShare/HDRScreenShare.exe`. Keep its whole directory.
Create the release ZIP and checksum after building:

```powershell
./scripts/package-release.ps1
```

Artifacts are written to `dist/releases`. Build products, development environments, local scratch files and logs are excluded from Git.

Source launch: `./run.ps1`. Diagnostic tools do not start Discord sharing:

```powershell
.venv/Scripts/python.exe tools/probe_lifecycle.py
.venv/Scripts/python.exe tools/probe_crash_cleanup.py
```

Run automated tests without attaching a display or starting Discord:

```powershell
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider
```

Native desktop probes can show the application or request UAC in Virtual screen mode. Run them manually on a Windows desktop.

## Troubleshooting

- **No picture:** select the HDR monitor, click Start and reopen Discord's source picker. For application mode choose **HDR Screen Share**, not the Controls window.
- **No window audio:** open Devices, install VB-CABLE from the vendor and keep headphones as the Windows default output. Enable application audio in Discord.
- **Virtual display fails to start:** install its signed driver through Devices and accept UAC when starting Virtual screen mode.
- **Reporting a problem:** include the app version, sharing mode, Windows version, monitor resolution/HDR state and relevant app-log messages. Do not include private screen or audio content.

## License

Original project sources are licensed under [MIT](LICENSE). Third-party components retain their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and [licenses](licenses/).
