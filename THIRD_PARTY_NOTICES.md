# Third-party software

This application uses Python, PySide6/Qt, NumPy and hdrcapture.

- hdrcapture 0.3.0: MIT. Copyright and license are included in licenses/hdrcapture-LICENSE.txt. Source: https://github.com/LDNKS094/hdrcapture/tree/v0.3.0
- PySide6 Essentials / Qt 6.12.0: upstream LGPL/GPL/commercial licensing terms and notices are included in licenses/PySide6. Source and licensing information: https://www.qt.io/qt-for-python and https://code.qt.io/cgit/pyside/pyside-setup.git/
- NumPy 2.5.4: upstream license and bundled dependency notices included in licenses/numpy.
- CPython 3.12.14: license and bundled dependency notices included in licenses/python-LICENSE.txt. Source: https://www.python.org/downloads/source/
- shiboken6 6.12.0: upstream notices included in licenses/shiboken6 when present.
- PyInstaller 6.22.3: build tooling and bootloader, upstream notices included in licenses/pyinstaller.

The portable build keeps shared libraries in the _internal folder. No dependencies or system settings are modified when the executable starts.
