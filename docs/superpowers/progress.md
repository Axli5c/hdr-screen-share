# SDD ledger — plan: docs/superpowers/plans/2026-10-17-hdr-discord.md

Execution: native, approved by user. Branch: codex/hdr-screen-share.
Ruling: use the project checkout on a separate feature branch; this fresh repository has only design documents and no existing implementation to isolate. No managed worktree created. Cost: changes remain visible in the current checkout.
Pre-flight: Task 1 supplies CaptureSource/LatestFrame/fit_size to Task 2; Task 2 supplies UI/entry point to Task 3. Interfaces consistent.
Task 1: started. Python 3.12.14; hdrcapture 0.3.0 CPython 3.12 Windows wheel installed from GitHub with SHA-256 verified by pip (5db899eab2c3bc441899f0b8e9fd87def906d948b2d78eaaaf0929ccdab8f118).
Ruling: keep a persistent tracked ledger here rather than Bash-only helper scripts unavailable in this PowerShell environment. Cost: manual bookkeeping.
Task 1: complete — real capture verified for SDR index 0 and HDR index 1 (2560×1440 BGRA8). Frame/source tests RED→GREEN; 13 passed before worker implementation.
Task 2: complete — worker and GUI tests RED→GREEN, 21 passed. Native HDR→SDR smoke: 460 captured and 460 painted over approximately 8 seconds; final interval 60.0 FPS capture and paint. Qt screen names are friendly names, not GDI names; mapping uses physical geometry, validated by regression test including reordered screens and DPI 150%.
Ruling: outside-screen output rejected after three controlled tests (Qt alone, GDI draw, one-pixel sliver). Native capture returned stale or black content. User explicitly approved using the second monitor; spec/plan amended accordingly. Cost: two monitors required, full 4K output requires adequate second-monitor resolution.
Ruling: commit implementation as a coherent prototype after packaging rather than separate task commits; sandbox restricts .git writes. Tests and evidence remain recorded here. Cost: coarser commit history.
Task 3: in progress — PyInstaller build succeeded outside sandbox; native runtime verification and independent review remain.
Final review: independent reviewer /root/review (gpt-6-astra) found two Important issues, no Critical: source launcher path quoting and output-monitor topology safety.
Final: fixed source launcher — reviewer reproduced unquoted app.py path failure; launch now uses '-m hdr_share' with PYTHONPATH, avoiding path splitting. An additional subprocess test exposed CLI help's Unicode arrow under cp1251; test_cli RED→GREEN after ASCII CLI description.
Final: fixed output topology — test_target_removal_or_reposition_stops_output_safely RED→GREEN; screen removal/geometry/DPI signals hide output immediately and stop capture, native topology additionally revalidated each second. Suite 23/23.
Final: Ruling: performance target remains unverified; sustained initial 2560×1440 benchmark averaged 57.21 capture / 57.16 paint FPS, despite short 60 FPS intervals. Deliver as prototype, record exact results and leave real4K60/Discord-client acceptance open. Cost: user must validate target performance before treating it as finished.
Final review: no deferred minor findings.
Task 3 packaging regression: first frozen exe hung before UI with Windows error 0xc0000139. Startup faulthandler traced QtCore import; PE import inspection found PyInstaller bundled Poppler's icuuc.dll instead of Windows ICU. Source QtCore import confirmed C:/Windows/System32/icuuc.dll. Exclude foreign ICU and its data DLL from payload; native frozen launch is the regression check.
Task 3: prototype deliverable complete — build succeeded; frozen exe regression RED→GREEN (exit0, 1150 captures/1129 paints in19.75s at2560×1440, no capture error); full pytest23/23. Full4K60 and end-to-end Discord remain unverified as the plan explicitly permits for a prototype. README and verification report preserve limitations.
Integration: preserve codex/hdr-screen-share in current checkout; no remote or merge requested. Portable build remains in dist/HDRScreenShare. No managed worktree to remove.
