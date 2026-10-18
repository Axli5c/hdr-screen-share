# HDR Screen Share 0.2.4

English · [Русский](README.ru.md)

Convert an HDR monitor to SDR for Discord while keeping local HDR enabled.

Windows x64 · Python + Direct3D/WASAPI · MIT · Preview

[Download](https://github.com/Axli5c/hdr-screen-share/releases/tag/v0.2.4) · [Changelog](CHANGELOG.md) · [Release notes](docs/releases/v0.2.4.md) · [License](LICENSE)

## Install the ready-to-run application

1. Open [release v0.2.4](https://github.com/Axli5c/hdr-screen-share/releases/tag/v0.2.4).
2. Under **Assets**, download **HDRScreenShare-v0.2.4-windows-x64.zip**. The **Source code** archives are for development and do not contain the ready-to-run program.
3. In File Explorer, right-click the downloaded ZIP and select **Extract All**. Choose a folder you can write to, such as Documents or a folder for portable applications.
4. Open the extracted **HDRScreenShare** folder and run **HDRScreenShare.exe**. Run the extracted copy, not the EXE inside the ZIP.
5. Keep the entire folder together. `_internal` contains the bundled runtime, libraries and native modules; copying only the EXE is not enough.
6. Choose a sharing mode and complete its setup below. The application opens idle and starts processing only after **Start**.

There is no separate application installer. For normal use, do not install Python, run pip, or build the source code. The interface is in English.

Use `SHA256SUMS.txt` from the same release to verify the ZIP:

```powershell
Get-FileHash .\HDRScreenShare-v0.2.4-windows-x64.zip -Algorithm SHA256
```

## Requirements and additional components

| Component | Do you need to install it separately? |
| --- | --- |
| Windows 11 x64 | Required; this is the tested platform. macOS, Linux, Windows ARM64 and 32-bit Windows builds are not provided. |
| HDR monitor and graphics driver | Enable HDR for the source monitor in Windows. The GPU/driver must support Direct3D 11. Use the normal driver for your graphics card. |
| Desktop Discord | Install or update it from the [official Discord download page](https://discord.com/download). Use its desktop application for filtered Discord-audio exclusion. |
| Python, PySide6/Qt, NumPy, hdrcapture | No. These are included in the portable folder. |
| Native audio/video modules and C/C++ runtime files | Included in the portable folder. Keep `_internal` intact. |
| Direct3D and WASAPI | Windows components; no separate package is needed. |
| VB-CABLE | Only for filtered sound in **Application window**. Installed separately; instructions below. Video can run without it, with an Audio unavailable status. |
| Virtual display driver | Only for **Virtual screen**. Install through the application's **Devices** dialog; instructions below. |

MSVC Build Tools, a Windows SDK and development Python packages are needed only when building from source, not when using the release ZIP.

If Windows reports a missing `MSVCP140.dll` or `VCRUNTIME140.dll` even with the full folder extracted, install or repair the official [Microsoft Visual C++ v14 Redistributable, x64](https://aka.ms/vc14/vc_redist.x64.exe) and reopen the app. See [Microsoft's runtime documentation](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist). This is a recovery step, not a Python-library installation.

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

Install only the component needed by the mode you intend to use. Both extra drivers are needed only if you plan to use both modes with audio.

### Application window: install VB-CABLE for audio

1. Open HDR Screen Share and choose **Application window**.
2. Open **Devices** and click **Get VB-CABLE (window mode)**. It opens the [official VB-Audio download page](https://vb-audio.com/Cable/); the app does not silently install the audio driver.
3. Download the Windows **VB-CABLE** package and extract all its files. Use the standard VB-CABLE package, not the separate A+B or C+D products.
4. Right-click **VBCABLE_Setup_x64.exe**, choose **Run as administrator**, approve UAC and click **Install Driver** in the vendor installer.
5. Restart Windows after installation, as instructed by [VB-Audio](https://vb-audio.com/Cable/). HDR Screen Share does not restart Windows for you.
6. In Windows sound settings, keep your headphones or speakers as the default playback device. Do not make **CABLE Input** the default system output. The installed cable exposes **CABLE Input** as a playback endpoint and **CABLE Output** as a recording endpoint; the app finds the playback endpoint automatically.
7. Reopen HDR Screen Share, select **Application window**, then **Devices → Refresh**. With a supported setup the dialog shows **Devices ready**.
8. Select your source monitor and click **Start**. Normal window capture does not request UAC and does not create a virtual monitor.
9. In Discord, share **HDR Screen Share** and enable application audio. Leave Discord's microphone input at your normal setting; the cable is used for the stream's application audio, not as your microphone.

If VB-CABLE is already installed and recognized by Devices, skip the download and installation. Without VB-CABLE, application-mode video can still run, but the filtered audio relay is unavailable.

### Virtual screen: install the display driver

1. Open HDR Screen Share and choose **Virtual screen**.
2. Open **Devices** and click **Install virtual display**. Internet access is needed for this one-time download.
3. The app downloads its supported signed driver package, checks its archive hash and publisher signatures, then requests UAC to install the dedicated adapter. Wait for completion; do not close the setup dialog while it is downloading or installing.
4. Click **Refresh** and check for **Devices ready**. If Windows explicitly requests a restart, restart manually before using the mode. The program never restarts the PC automatically.
5. Close Devices, choose the source monitor and click **Start**. Approve the separate UAC request that enables the adapter for this session. This request occurs at each screen-mode Start, not only during installation.
6. In Discord, share the screen number shown by the app and enable Discord's system-audio option. VB-CABLE is not required for this mode.
7. Use **Stop** or close the app when finished. The virtual monitor is removed from display enumeration; its driver stays installed for the next Start.

If the dedicated driver is already installed, Devices recognizes it even while its adapter is disabled; reinstalling it for each session is unnecessary. The installer does not adopt or overwrite a different existing Virtual Display Driver installation. Use Application window mode or resolve that existing installation before setting up this mode.

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
