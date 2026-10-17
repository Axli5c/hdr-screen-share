"""Native controls/comparison probe. One UAC prompt; never starts Discord sharing."""
import json
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from hdr_share.monitors import enable_physical_pixels, list_sources
from hdr_share.ui import ControlWindow
from hdr_share.virtual_display import WindowsDisplayBackend


def main():
    enable_physical_pixels()
    before = list_sources()
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    window = ControlWindow(default_mode='application')
    window.show()
    results, errors = {}, []
    def guarded(function):
        def call():
            try:
                function()
            except Exception as error:
                errors.append(str(error))
                window.close()
                app.quit()
        return call
    def start():
        results['idle_without_worker'] = window.worker is None and not window.controller.running
        results['idle_physical_unchanged'] = before == list_sources()
        window.compare_toggle.setChecked(True)
        window.start_button.click()
        if not window.controller.running:
            raise RuntimeError(window.status.text())
        QTimer.singleShot(5500, guarded(compare))
    def compare():
        results['before_live'] = not window.before_preview.image.isNull()
        results['after_live'] = not window.preview.image.isNull()
        results['comparison_status'] = window.comparison_status.text()
        results['video_status'] = window.status.text()
        results['audio_status'] = window.audio_status.text()
        results['display_status'] = window.display_status.text()
        results['output_size'] = window.output.output_size
        results['captured'] = window.worker.captured
        results['presented'] = window.output.presented
        window.grab().save(str(Path('.scratch/controls-v023.png').resolve()))
        window.compare_toggle.setChecked(False)
        QTimer.singleShot(500, guarded(finish))
    def finish():
        results['raw_released_when_off'] = window.worker.comparison_frames.latest_after(0) is None
        results['stop_ok'] = window.stop_capture()
        results['physical_restored'] = before == list_sources()
        results['adapter_absent'] = WindowsDisplayBackend().owned_display() is None
        window.close()
        app.quit()
    QTimer.singleShot(700, guarded(start))
    app.exec()
    results['errors'] = errors
    results['passed'] = (not errors and all(results.get(key) for key in
        ['idle_without_worker', 'idle_physical_unchanged', 'before_live', 'after_live',
         'raw_released_when_off', 'stop_ok', 'physical_restored', 'adapter_absent']))
    print(json.dumps(results, ensure_ascii=True))
    return 0 if results['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
