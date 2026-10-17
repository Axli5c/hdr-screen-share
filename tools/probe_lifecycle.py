"""Bounded native GUI lifecycle check; does not start Discord sharing."""
import ctypes as C
from ctypes import wintypes as W
import json

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from hdr_share.monitors import enable_physical_pixels, list_sources
from hdr_share.ui import ControlWindow


def main():
    enable_physical_pixels()
    before = list_sources()
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    window = ControlWindow()
    window.show()
    result = {}
    counts = {}
    errors = []

    def guard(function):
        def call():
            try:
                function()
            except Exception as error:
                errors.append(str(error))
                window.close()
                app.quit()
        return call

    def minimize():
        counts['preview'] = window.preview.received
        counts['output'] = window.output.received
        window.showMinimized()

    def restored():
        result['preview_paused'] = window.preview.received == counts['preview']
        result['stream_continued'] = window.output.received > counts['output']
        window.showNormal()
        api = C.WinDLL('user32', use_last_error=True)
        api.GetWindowDisplayAffinity.argtypes = [W.HWND, C.POINTER(W.DWORD)]
        control, output = W.DWORD(), W.DWORD()
        if not api.GetWindowDisplayAffinity(int(window.winId()), C.byref(control)):
            raise C.WinError(C.get_last_error())
        if not api.GetWindowDisplayAffinity(int(window.output.winId()), C.byref(output)):
            raise C.WinError(C.get_last_error())
        result['control_affinity'], result['output_affinity'] = control.value, output.value
        result['audio_status'] = window.audio_status.text()
        result['output_source'] = window.controller._target_id
        result['output_visible_on_virtual'] = (window.output.x() >= max(s.left + s.width for s in before))

    def restart():
        result['first_stop'] = window.stop_capture()
        result['topology_restored_on_stop'] = list_sources() == before
        window.start_capture()

    def finish():
        result['restart_running'] = window._running and window.worker.captured > 0
        result['audio_stats'] = window.controller.audio.stats() if window.controller.audio else None
        window.close()
        result['topology_restored_on_close'] = list_sources() == before
        app.quit()

    for delay, function in ((1800, minimize), (3200, restored), (4300, restart), (7000, finish)):
        QTimer.singleShot(delay, guard(function))
    app.exec()
    result['errors'] = errors
    result['passed'] = (not errors and result.get('preview_paused') and result.get('stream_continued')
        and result.get('control_affinity') == 0x11 and result.get('output_affinity') == 0
        and result.get('output_visible_on_virtual') and result.get('first_stop')
        and result.get('restart_running') and result.get('topology_restored_on_stop')
        and result.get('topology_restored_on_close'))
    print(json.dumps(result, ensure_ascii=True))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
