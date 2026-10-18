# Installer verification — 2026-10-18

Artifact: `HDRScreenShare-Setup-v0.2.4-windows-x64.exe`. The enclosed application executable remains the previously tested v0.2.4 binary. Setup sources are maintained on the repository's main branch; the original v0.2.4 application tag is unchanged.

Validated on Windows 11 x64:

- 109 automated tests pass, including 12 PowerShell coordinator tests for selection, skipping existing components, independent failure results, bad archive hashes, publisher matching and installer exit codes and persisted completion status.
- Both actual official driver URLs were downloaded using the new helper. Their pinned SHA-256 values, archive members and publisher signatures passed. No driver installers were executed by this download check.
- Existing dedicated VDD and working VB-CABLE were detected and skipped. A second old failed VB-CABLE devnode did not cause a working installation to be overwritten.
- Core-only Setup installed into an isolated path containing spaces under the ordinary desktop user, without elevation. The installed application opened its Controls window, remained idle and closed normally.
- Core-only uninstallation returned zero and removed the application executable. The dedicated virtual adapter remained disabled (device problem code 22).
- Code review corrected the 32-bit installer's path to native 64-bit PowerShell, added an explicit completion marker for elevated setup results, and restricted the installer to actual x64 Windows because the pinned display kernel driver does not support ARM64.
- The first sandbox-identity attempt could not resolve the Windows localappdata shell folder. The same installer succeeded under the normal desktop identity; this is not a supported end-user execution environment.

Not yet validated: a fresh Windows installation with absent drivers, completion of the VB-Audio silent installer on that fresh system, UAC cancellation through the final wizard, or the wizard's visual layout at every display scaling setting. Native installation is limited to the original signed vendor packages; certificates are not imported and Windows is not restarted automatically. Windows may select a newly installed audio device as default; the finish page and instructions tell the user to keep their headphones and microphone selected.

Actual Discord receiver/video/audio checks and real HDR 4K60 remain as described in [application verification](verification-v024.md).
