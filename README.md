# HDR Screen Share 0.2.3

Convert an HDR monitor to SDR for Discord while keeping local HDR enabled.

## Use

1. Run `dist/HDRScreenShare/HDRScreenShare.exe`. Keep `_internal` beside it.
2. Choose your monitor and sharing mode.
3. Click **Start** and approve Windows UAC to enable the virtual display for this session.
4. Select the source shown by the app in Discord and enable its audio toggle.

**Virtual screen** (default): share the processed SDR screen with Discord system audio. VB-CABLE is not needed for this mode.

**Application window**: share **HDR Screen Share** with application audio. This mode uses the existing VB-CABLE relay to mix application/game audio while excluding desktop Discord and this app. Physical microphone devices are not opened.

The app opens idle. Video, Audio and Display show separate statuses. Enable **Before / After** for two small previews: the source without tone mapping and the processed SDR output. The Before preview clips raw scRGB to SDR for display; it is an illustration of unmapped highlights, not a reproduction of Discord's private capture pipeline. The raw preview is sampled at up to5FPS, starts only when enabled and pauses while the app is minimized. Comparison failures do not stop the SDR stream.

The control window can be minimized. Full-size output stays on the app-owned virtual display. Stop/close completely disables the dedicated virtual adapter, removing the monitor from Windows display enumeration. A temporary UAC-approved helper also disables it after the main app process crashes. The driver package remains installed for the next Start; no permanent service is installed. Physical screens are not duplicated or reconfigured.

## One-time setup

Open **Devices**. Install the signed virtual display driver once. Application-window audio additionally needs the original [VB-CABLE installer](https://vb-audio.com/Cable/), linked only in that mode. Keep your headphones as Windows' default output. Each Start requests UAC for the temporary display helper. The control window, video and audio run without elevation. Setup and normal use do not reboot automatically.

## Details

Video supports up to3840×2160 (portrait2160×3840), without upscaling. Preview is480×270 at up to15FPS. Frame counters measure local capture/painting, not Discord viewer FPS.

Discord controls system audio and screen captions in Virtual screen mode. The application's Discord exclusion filter applies only to Application window mode. System/unsupported audio sessions are excluded from the application relay. Browser Discord tabs cannot be isolated from other browser audio; use desktop Discord for filtered sharing.

FullHDR4K60, A/V drift and viewer delivery remain unverified. Local screen/audio and cleanup measurements are in `docs/verification-v2.md`, `docs/verification-v021.md` and `docs/verification-v023.md`. Ordinary use does not save frames or audio. App log: `%LOCALAPPDATA%/HDRScreenShare/app.log`.

## Build

CPython3.12x64, MSVC x64 Build Tools and Windows SDK are required for development only.

```powershell
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
./build.ps1
```

Source launch: `./run.ps1`. Diagnostic tools do not start Discord sharing:

```powershell
.venv/Scripts/python.exe tools/probe_lifecycle.py
.venv/Scripts/python.exe tools/probe_crash_cleanup.py
```
