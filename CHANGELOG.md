# Changelog

## 0.2.4 — 2026-10-18

- Application window uses a Direct3D SDR output outside the visible desktop.
- Application window no longer enables a virtual monitor, requires its driver, or requests UAC.
- Virtual screen retains its dedicated virtual display and automatic cleanup.
- Added safe mode switching, GPU output error handling and bounded scaling for oversized sources.
- Validated with 97 automated tests and native/frozen capture probes.

## 0.2.3 — 2026-10-18

- Open idle; begin processing only after Start.
- Separate Video, Audio and Display statuses.
- Optional Before / After previews.
- Completely disable the owned virtual adapter on Stop, exit or parent-process crash.
- Temporary UAC-approved display helper with cleanup ownership and retries.

## 0.2.2 — 2026-10-18

- Remove the output window's no-activation flag so it meets ordinary Windows application-list prerequisites.
- Preserve focus when showing the output.

## 0.2.1 — 2026-10-18

- Add Virtual screen and Application window sharing modes.
- Let Discord handle system audio in Virtual screen mode.
- Retain filtered application/game audio in Application window mode.
- Simplify the English interface and add owned-display crash cleanup.
