# HDR Screen Share v2 — verification in progress

2026-10-17, Windows build 26300, Python 3.12 x64.

## Devices

- VDD archive SHA-256: F93E7CE3D640C83C419B1B72D2C83B2D8E34D83E8B7BA11F3328A40D2DA82FA4.
- CAT and DLL: Authenticode Valid, SignPath Foundation. INF catalog membership independently verified with Windows SDK signtool `/pa /c`: success.
- Installed dedicated PnP instance `ROOT\HDRSCREENSHAREVDD\0000`, published INF `oem156.inf`; no trust roots/test-signing/Secure Boot changes or reboot.
- Confirmed interface identity via DisplayConfig adapter path, not shared `Root\MttVDD` hardware ID or friendly name.
- Advertised modes: 800×600, 1366×768, 1920×1080, 2560×1440, 3840×2160, 2160×3840, all 60 Hz/32 bpp.
- Native acquire→release→acquire at 3840×2160 SDR succeeded. Physical source list equal before/after; primary HDR remained active.
- Six-second synthetic WGC window probe: size 3840×2160, both expected color channels observed, 94 grabs, no error, physical topology unchanged. This checks capture correctness, **not** unique 60 FPS or Discord.
- Initial installer XML preparation error reproduced and fixed using SelectSingleNode; regression test exercises Windows PowerShell 5.1. A subsequent PowerShell registry-provider error left preparation only; resumed via exact files/values validation and RegistryKey API. Driver registered only after successful preparation.
- Idle dedicated display is detached.

## Audio / release criteria

VB-CABLE archive SHA-256: B950E39F01AF1D04EA623C8F6D8EB9B6EA5C477C637295FABF20631C85116BFB. Original vendor setup was launched independently. During device initialization CABLE Input was absent and a duplicate MEDIA devnode showed code10; it subsequently became active without reboot. No automatic removal of duplicate/foreign audio devices. Logitech headset remained default for all three render roles.

Native relay rejects the physical headset endpoint with 0x80070005. Synthetic probe passed: permitted700/1100Hz amplitudes0.01270/0.01268, excluded1700Hz -112.33dB, 242400outputframes, queue480frames, no overflows, HRESULT0, defaults unchanged. Probe records only virtual cable in memory and saves no audio; independent tone helpers exercise Discord.exe exclusion.

User has no second Discord client/helper available and explicitly deferred that test. Actual Discord audio/window delivery, sustained4K/60 and A/V drift remain pending. No v2 release is claimed.

## GUI and portable build

- Native lifecycle probe PASS: minimize pauses preview only; stream continues; control capture affinity0x11, stream affinity0; output on virtual display; stop/restart/close restore the original physical topology.
- Native general audio initially failed closed on an inaccessible active Audiosrv PID. Exact service PID is now identified through SCM and excluded as unsupported; system/non-single-process sessions are not captured. Other unknown active audio processes still fail closed. UI explicitly reports unavailable system sounds.
- Portable0.2 exe passed clean PATH/PYTHONPATH startup from a path with spaces, exit0. Real2560×1440:678captures/672Qtpaints over11.344s, 59.77/59.24FPS; audio544800frames, queue0, overflows0, HRESULT0. Qt paint count is not Discord viewer FPS.
- Separate initial4K synthetic probe (10s,17ms timer):572Qtpaints,497unique WGC captures; 57.2/52.32FPS. FullHDR4K60 not established. Subsequent timing/performance checks are recorded below when available.
