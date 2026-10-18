# HDR Screen Share

English · [Русский](README.ru.md)

Share an HDR screen in Discord without washed-out highlights. The app converts captured video to SDR while keeping HDR enabled on your own monitor.

**Windows 11 x64 · Preview · MIT**

[Download](https://github.com/Axli5c/hdr-screen-share/releases) · [Changelog](CHANGELOG.md) · [Report an issue](https://github.com/Axli5c/hdr-screen-share/issues)

## Install

1. Download **HDRScreenShare-Setup-v…-windows-x64.exe** from the latest release and run it.
2. Choose English or Russian for Setup. Python and app libraries are included; the app UI is English.
3. Optionally select drivers in Setup. You can also install them later from the app.
4. On launch, **Dependencies** opens if anything needs attention:
   - **✓ Ready** — the component is available.
   - **✗** — missing: choose **Install** or **Download / instructions**.
   - **⚠** — configuration, a Windows restart, or a repair is needed.

Checks run at startup, when returning to the app, while Dependencies is open, and through **Check again**. A checkmark requires a successful availability check. Driver installation needs administrator approval; automatic downloads need internet access. The app never restarts Windows automatically.

**Portable:** download the ZIP, extract everything, and run `HDRScreenShare.exe`. Keep the `_internal` folder beside it.

## Share

Select the source monitor and mode, click **Start**, then choose the source in Discord. **Stop** ends capture. Nothing is captured before Start.

| Mode | Dependency | Select in Discord |
| --- | --- | --- |
| **Virtual screen** | Virtual Display Driver | The screen number shown by the app; enable system audio |
| **Application window** | VB-CABLE for audio | **HDR Screen Share**; enable application audio |

Install only the driver for the mode you need. A missing driver for the other mode does not block you. Virtual screen requests UAC on each Start and disables its virtual screen on Stop or exit. Application window does not create a virtual monitor.

**Before / After** compares the original and converted image. Output supports up to 4K with a 60 FPS target; actual streaming quality depends on your computer and Discord.

## Install drivers manually

- **VB-CABLE:** visit [VB-Audio](https://vb-audio.com/Cable/), download standard VB-CABLE, extract the archive, and run `VBCABLE_Setup_x64.exe` as administrator. Click **Install Driver**, then restart Windows. Keep headphones/speakers as the default output and your microphone as the default input. VB-CABLE is donationware by VB-Audio.
- **Virtual Display Driver:** download `Signed-Driver-v24.12.24-x64.zip` from the [supported release](https://github.com/VirtualDrivers/Virtual-Display-Driver/releases/tag/25.5.2). In **Dependencies**, choose **Install downloaded VDD ZIP…**. The app verifies the package and registers its dedicated adapter. A generic VDD installation does not replace this step; the app will not overwrite another installation's adapter.

After installation, click **Check again**. If you see **Restart Windows**, restart Windows itself, not just the app.

## Troubleshooting

- **Setup did not install a driver:** open **Dependencies** and retry, or download it manually. The window shows errors and the installation report path.
- **VB-CABLE is installed but unavailable:** open **Windows sound settings**, enable CABLE Input, and keep headphones/speakers as the default output.
- **No picture in Discord:** click Start and reopen the source picker. In window mode, select **HDR Screen Share**, not **Controls**.
- **No sound:** check Dependencies and enable audio sharing in Discord. Use desktop Discord to exclude its voice audio from the application relay; a Discord browser tab cannot be separated from other browser audio.

Log: `%LOCALAPPDATA%/HDRScreenShare/app.log`. In-app installation reports: `%LOCALAPPDATA%/HDRScreenShare/setup/`. Include the app version, mode, Windows version, and error text when reporting a problem.

This is a preview: sustained 4K60, audio/video sync, and the final Discord viewer experience have not yet been validated. Normal use does not save video frames or audio.

## Build from source

Development needs Python 3.12 x64, MSVC Build Tools with C++, and the Windows SDK. Setup also needs Inno Setup 6.7+.

```powershell
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
./build.ps1
./scripts/package-release.ps1
./scripts/build-installer.ps1
```

App: `dist/HDRScreenShare/`. Packages: `dist/releases/`. Source launch: `./run.ps1`. Tests: `.venv/Scripts/python.exe -m pytest -q`.

[MIT license](LICENSE) · [Third-party notices](THIRD_PARTY_NOTICES.md)
