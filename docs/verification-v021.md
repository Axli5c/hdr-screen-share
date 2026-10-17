# v0.2.1 — capture modes and idle display cleanup

Approved bounded change, 2026-10-18:

- Virtual screen (default): same HDR→SDR video, Discord owns system-audio capture. No native audio relay, VB-CABLE endpoint lookup or microphone client is started.
- Application window: output title HDR Screen Share, existing filtered app audio via VB-CABLE.
- English UI with monitor/mode/preview/Start/Stop/Refresh and short sharing instructions. Device setup requires only the display driver in screen mode; VB-CABLE is offered only for application mode.
- Own virtual display detached on stop/exit, even if it was active before startup or its mode changed. Latest user instruction overrides the previous preserve-own-output-mode ruling; physical and foreign displays stay untouched.
- Separate watchdog starts before attachment, waits for the original parent process, acquires the display lock and detaches only the identified app-owned output after a crash. No scheduled task, service or additional driver.

Tests: modes/guard policy/UI tests observed RED→GREEN; 77 pytest tests pass. Source native crash probe PASS (probe-owned app process forcibly terminated; virtual screen detached; physical topology restored). Source screen-mode smoke PASS, audio_stats null, no relay. Portable build and final probes recorded below when available.

Final portable0.2.1: native mixer/77pytest/compileall/PyInstaller PASS. Frozen crash probe PASS: own screen detached after termination, physical topology restored. Both frozen modes exit0: screen mode audio_stats null; application mode audio163200frames, queue0, overflows0, HRESULT0. Output inactive after both modes close. English UI screenshot inspected. Focused independent review /root/review_modes reported no Critical/Important defects. No driver changes, reboot or Discord broadcast.

Discord chooses screen-list captions; the app shows the Windows screen number, while its application-window title is controlled by the app. Actual viewer/audio delivery and full4K60 acceptance remain deferred from v0.2.0. Whole-system audio in screen mode uses Discord's behavior, not the application-mode Discord exclusion filter.

## v0.2.2 — application-window enumeration correction (2026-10-18)

User reports the output absent from Discord's application list. Native inspection found the visible, unowned output had WS_EX_NOACTIVATE (0x08000000), which suppresses default taskbar listing. Removed Qt WindowDoesNotAcceptFocus while retaining WA_ShowWithoutActivating. Output remains frameless on the owned virtual display.

Extended tools/probe_virtual_stream.py with native EnumWindows/title/visibility/owner/style checks and a foreground-preservation check. These check ordinary Windows application-list prerequisites; they do not invoke Discord's private enumeration or prove its picker result. RED before the fix: extended_style 0x8000000, application_list_eligible false. GREEN after: extended_style 0x0, eligible true, focus preserved; synthetic 3840x2160 WGC capture contains both expected colors, physical topology restored. This short low-FPS probe is not a 4K60 acceptance test.

Build: native mixer tests, 77 pytest tests, compileall and PyInstaller pass. Lifecycle probe passes preview pause/stream continuation, affinity separation, stop/restart and display cleanup. Frozen application mode exits 0: native output enumerated visible/eligible, 306 captured / 292 presented frames, no capture error; audio queue 480, overflows 0, HRESULT 0. Display topology restored on close. The first frozen probe sampled the hidden HWND before show; corrected the probe to wait for visible eligibility and reran successfully. Actual Discord picker visibility and viewer reception require user verification.
