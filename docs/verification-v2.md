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

- Final separate4K synthetic measurement: 5s warmup, exactly60s measured,3840×2160/60Hz virtual SDR; 3750Qtpaints (62.5/s with16ms producer timer),3533unique CPU-readback WGC frames (58.883/s). Physical topology restored. Qt paint events can exceed display refresh and do not prove distinct DWM presents. The unique WGC result is below the59FPS acceptance threshold. This was not a full4K HDR source and no end-to-end4K60 claim is made. CPU/GPU profiling and ten-minute A/V drift are unmeasured.
- Whole-branch review found two reproducible Important display-cleanup failures and one native source-exit code-path concern. Display failures reproduced RED and fixed GREEN: precomputed cleanup state saved before attachment, mutex/lease retained on failure, controller retries release. Native source-exit probe already passed before changes; hardened using retained process handles and per-source queue removal, then re-tested PASS (surviving amplitude0.01268, HRESULT0). No claim that a normal-exit audio failure was observed.
- After fixes:71pytest tests pass, native mixer tests pass, synthetic source-exit probe and native GUI lifecycle probe pass. Actual Discord viewer testing remains deferred by user.
- Final rebuilt exe: FileVersion/ProductVersion0.2.0; clean PATH/PYTHONPATH smoke exit0.552captures/544Qtpaints over9.344s (59.08/58.22FPS) at2560×1440; audio447840frames, queue0, overflows0, HRESULT0. Current default recording endpoint is the physical Logitech G735 microphone for all three roles (properties read only; no recording client opened). Portable folder306files/155773544bytes before final documentation synchronization.

This delivers the v0.2 diagnostic prototype. The unresolved acceptance criteria are explicit: actual Discord source listing/audio received by a second client, sustained full HDR4K60, and measured A/V skew/drift. No production-performance assertion is made.
