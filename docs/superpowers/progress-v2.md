# SDD ledger — plan: docs/superpowers/plans/2026-10-17-hdr-discord-v2.md

Spec: docs/superpowers/specs/2026-10-17-hdr-discord-v2-design.md

User approved the plan and signed device installation. Execution continues inline.

Ruling: retain the existing codex/hdr-screen-share checkout and tracked ledger — this preserves the earlier workspace ruling and user workflow — no parallel implementation checkout.

Pre-flight interfaces:
- Task 1 → 3: DisplayLease returns CaptureSource and releases only its own device; controller must hide output before releasing. Consistent.
- Task 2 → 3: AudioRelay owns native audio resources, reports errors independently of video. Consistent.
- Task 3 → 4: one immutable latest frame with separate consumer sequences; packaging retains native DLL and ICU exclusion. Consistent.

Baseline: 23 pytest tests passed (2026-10-17).

Task 1: in progress. Signed archives staged, not installed. Checking pinned driver source before selecting a safe ownership mechanism.

Tasks 2–4: pending. Discord end-to-end audio and 4K/60 remain unverified.

2026-10-17: package integrity/signature policy and lease boundary tests: RED (missing modules), GREEN 11 passed. Windows backend intentionally remains fail-closed until device registration/identity is implemented; Task 1 not complete.

Pinned driver source confirms SETDISPLAYCOUNT reinitializes adapter and maps count 0 to 1 (Driver.cpp lines 1028–1043, 1318–1319).
Ruling: use per-display Windows attach/detach instead of global IPC — preserves foreign monitors and allows idle removal — requires validated PnP-to-GDI identity after installation.

Ruling: implement independent audio policy tests while installation mechanics are being prepared — no runtime/UI dependency on unverified drivers — Task 2 remains incomplete until native path and actual probe exist.

VDD installed: exact dedicated ROOT\HDRSCREENSHAREVDD\0000, oem156.inf. Authenticated archive/SignPath signatures and INF catalog membership checked. Initial PowerShell XML/registry preparation failures diagnosed; no devnode registered until successful preparation. XML regression test RED→GREEN under PowerShell 5.1.

Native display lifecycle: 3840×2160 SDR/60 acquire→release→acquire succeeded. Detached indirect adapter requires stage (CDS_NORESET) then commit the same named device; immediate mode change fails. No global NULL-device commit used. Full PnP identity resolved via DisplayConfig interface; EnumDisplayDevices exposes hardware ID only.

Synthetic virtual-window WGC probe: PASS, 3840×2160, 2 expected colors, 94 grabs in six seconds; physical topology equal before/after. Not a frame-rate or Discord acceptance result. Idle virtual display detached.

Ruling: do not integrate VB-CABLE package into application installation — original package readme prohibits integration without author agreement — use separate vendor setup; no redistribution in our payload.

Task 1: display package/installation/lifecycle/probe complete. VB-CABLE installed through original separate setup. During initialization render endpoint temporarily absent and duplicate MEDIA devnode reported code 10; later actual CABLE Input became active. No reboot performed. Do not remove foreign/duplicate devnodes automatically.

Task 2: native DLL + Python policy/lifecycle implemented. Synthetic audio probe PASS: permitted 700/1100 Hz amplitudes 0.01270/0.01268; excluded Discord.exe 1700 Hz -112.33 dB, output242400frames, maximum reported queue480frames, zero overflows, HRESULT0; default render endpoints unchanged. Probe uses sibling tone/relay processes so own-child exclusion remains enforced. No microphone or audio file recording.

Physical headset endpoint rejected by native relay with E_ACCESSDENIED (0x80070005). Native mixer tests pass; pytest55/55 before mailbox task.

User explicitly answered no second Discord client/helper available: leave actual Discord application-audio delivery open. Ruling: proceed with Task 3 prototype as plan permits; no end-to-end success or release claim.

Task 3: started; mailbox tests RED, implementing independent consumers.

Task 3: complete for prototype. FrameMailbox immutable bytes-backed latest frame; full output and preview have independent sequences. New StreamController owns ordered display/audio/video lifecycle. Preview480×270/15FPS, control-only WDA0x11, full output WDA0. Control source list excludes owned output. GUI/controller tests RED→GREEN. Additional regression catches borrowed preview pixels at exactly480×270; fixed by owning the small QImage copy.

Native lifecycle probe PASS: preview pauses on minimize while output continues; full output only on virtual screen; stop/restart/close restore physical topology; control affinity17/output0. Real2560×1440 frozen smoke exits0 with678captures/672paints in11.344s (59.77/59.24FPS), native audio544800frames, zero queue/overflows/HRESULT0. Clean PATH/PYTHONPATH, path with spaces.

Ruling: exclude only positively identified Audiosrv/service or system/non-single-process sessions as unsupported and show warning — process loopback cannot isolate those safely and monitoring could reintroduce mic/relay — all other unknown active PIDs still fail closed. Evidence: active session PID3648 maps via SCM to Audiosrv, inaccessible process identity. IsSystemSoundsSession alone was insufficient (S_FALSE); service query adds exact identity exclusion. General native audio smoke now works.

Task 4: in progress. Initial build test failure was shared temporary-directory ACLs between sandbox/desktop identities; build now allocates a fresh GUID test directory and disables pytest cache. Full66tests/native mixer/build passed before latest preview regression. v0.2 frozen smoke passed. Final benchmark, review, documentation sync remain.
