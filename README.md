# HDR Screen Share 0.2.1

Convert an HDR monitor to SDR for Discord while keeping local HDR enabled.

## Use

1. Run `dist/HDRScreenShare/HDRScreenShare.exe`. Keep `_internal` beside it.
2. Choose your monitor and sharing mode.
3. Select the source shown by the app in Discord and enable its audio toggle.

**Virtual screen** (default): share the processed SDR screen with Discord system audio. VB-CABLE is not needed for this mode.

**Application window**: share **HDR Screen Share** with application audio. This mode uses the existing VB-CABLE relay to mix application/game audio while excluding desktop Discord and this app. Physical microphone devices are not opened.

The control window shows a small preview and can be minimized. Full-size output stays on the app-owned virtual display. Stop/close detaches that display. A lightweight watchdog also detaches it after the main app process crashes. Physical screens are not duplicated or reconfigured.

## One-time setup

Open **Devices**. Install the signed virtual display driver. Application-window audio additionally needs the original [VB-CABLE installer](https://vb-audio.com/Cable/), linked only in that mode. Keep your headphones as Windows' default output. Normal use does not need administrator rights. Driver setup uses Windows UAC and does not reboot automatically.

## Details

Video supports up to3840×2160 (portrait2160×3840), without upscaling. Preview is480×270 at up to15FPS. Frame counters measure local capture/painting, not Discord viewer FPS.

Discord controls system audio and screen captions in Virtual screen mode. The application's Discord exclusion filter applies only to Application window mode. System/unsupported audio sessions are excluded from the application relay. Browser Discord tabs cannot be isolated from other browser audio; use desktop Discord for filtered sharing.

FullHDR4K60, A/V drift and viewer delivery remain unverified. Local screen/audio and crash-cleanup measurements are in `docs/verification-v2.md` and `docs/verification-v021.md`. Ordinary use does not save frames or audio. App log: `%LOCALAPPDATA%/HDRScreenShare/app.log`.

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
