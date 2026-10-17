# Third-party software

This application uses Python, PySide6/Qt, NumPy and hdrcapture.

- hdrcapture 0.3.0: MIT. Copyright and license are included in licenses/hdrcapture-LICENSE.txt. Source: https://github.com/LDNKS094/hdrcapture/tree/v0.3.0
- PySide6 Essentials / Qt 6.12.0: upstream LGPL/GPL/commercial licensing terms and notices are included in licenses/PySide6. Source and licensing information: https://www.qt.io/qt-for-python and https://code.qt.io/cgit/pyside/pyside-setup.git/
- NumPy 2.5.4: upstream license and bundled dependency notices included in licenses/numpy.
- CPython 3.12.14: license and bundled dependency notices included in licenses/python-LICENSE.txt. Source: https://www.python.org/downloads/source/
- shiboken6 6.12.0: upstream notices included in licenses/shiboken6 when present.
- PyInstaller 6.22.3: build tooling and bootloader, upstream notices included in licenses/pyinstaller.

The portable build keeps shared libraries in the _internal folder. Native audio_bridge.dll is built from this project's native sources using Windows WASAPI interfaces. Process-loopback API reference: https://learn.microsoft.com/en-us/samples/microsoft/windows-classic-samples/applicationloopbackaudio-sample/

Virtual Display Driver 24.12.24 is downloaded independently from https://github.com/VirtualDrivers/Virtual-Display-Driver/releases/tag/25.5.2 with a pinned archive hash and verified SignPath signatures. Its driver binaries are not part of this portable payload. VB-CABLE belongs to Vincent Burel / VB-Audio, https://vb-audio.com/Cable/ ; it is installed separately from the original vendor package and is not bundled or integrated into our installation procedure. Vendor licensing: https://vb-audio.com/Services/licensing.htm

Only the explicit one-time display installation helper receives Windows elevation. Normal streaming opens/closes the app-owned virtual display and routes the relay exclusively to the selected virtual playback endpoint; no microphone device is opened and default devices are not changed.
