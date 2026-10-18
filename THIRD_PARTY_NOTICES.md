# Third-party software

This application uses Python, PySide6/Qt, NumPy and hdrcapture.

- hdrcapture 0.3.0: MIT. Copyright and license are included in licenses/hdrcapture-LICENSE.txt. Source: https://github.com/LDNKS094/hdrcapture/tree/v0.3.0
- PySide6 Essentials / Qt 6.12.0: upstream LGPL/GPL/commercial licensing terms and notices are included in licenses/PySide6. Source and licensing information: https://www.qt.io/qt-for-python and https://code.qt.io/cgit/pyside/pyside-setup.git/
- NumPy 2.5.4: upstream license and bundled dependency notices included in licenses/numpy.
- CPython 3.12.14: license and bundled dependency notices included in licenses/python-LICENSE.txt. Source: https://www.python.org/downloads/source/
- shiboken6 6.12.0: upstream notices included in licenses/shiboken6 when present.
- PyInstaller 6.22.3: build tooling and bootloader, upstream notices included in licenses/pyinstaller.

The project's original Python, C++ and build-script sources are licensed under MIT; see LICENSE. The third-party components below retain their own licenses.

The portable build keeps shared libraries in the _internal folder. Native audio_bridge.dll and video_presenter.dll are built from this project's native sources using Windows WASAPI and Direct3D interfaces. Process-loopback API reference: https://learn.microsoft.com/en-us/samples/microsoft/windows-classic-samples/applicationloopbackaudio-sample/

Virtual Display Driver 24.12.24 is downloaded independently from https://github.com/VirtualDrivers/Virtual-Display-Driver/releases/tag/25.5.2 with a pinned archive hash and verified SignPath signatures. Its driver binaries are not part of this portable payload. VB-CABLE belongs to Vincent Burel / VB-Audio, https://vb-audio.com/Cable/ ; it is installed separately from the original vendor package and is not bundled or integrated into our installation procedure. Vendor licensing: https://vb-audio.com/Services/licensing.htm

The explicit one-time display installation helper and the temporary Virtual screen session helper receive Windows elevation. Application window mode does not enable a virtual display or request elevation. The application-mode audio relay uses the VB-CABLE playback endpoint; microphone devices are not opened and Windows default audio devices are not changed.
