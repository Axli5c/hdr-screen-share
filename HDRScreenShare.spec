# Portable folder: Qt DLLs remain separate and replaceable.
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all('hdrcapture')
a = Analysis(['app.py'], pathex=['src'], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports,
             runtime_hooks=['packaging_diagnostics.py'],
             excludes=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
                       'PySide6.QtPdf', 'PySide6.QtQml', 'PySide6.QtQuick',
                       'pytest', 'tkinter'], noarchive=False)
# Qt uses the Windows system ICU API. A Poppler installation on PATH can make
# PyInstaller collect its incompatible, version-suffixed ICU under the same
# icuuc.dll name (startup error 0xc0000139). Leave Windows ICU to the OS loader.
a.binaries = [entry for entry in a.binaries
              if entry[0].lower() not in {'icuuc.dll', 'icuin.dll', 'icudt78.dll'}]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='HDRScreenShare',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='HDRScreenShare')
