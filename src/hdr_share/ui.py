import time

import numpy as np
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPainter, QColor, QColorSpace
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                              QLabel, QComboBox, QPushButton, QCheckBox)

from .capture import CaptureWorker
from .frames import LatestFrame, fit_size
from .monitors import list_sources, default_source


def choose_output(ids: list[str], captured: str, previous: str | None) -> str | None:
    candidates = [identifier for identifier in ids if identifier != captured]
    return previous if previous in candidates else next(iter(candidates), None)


def output_dimensions(width, height, screen_width, screen_height):
    width, height = fit_size(width, height)
    scale = min(1, screen_width / width, screen_height / height)
    return max(1, round(width * scale)), max(1, round(height * scale))


def screen_for_source(identifier):
    source = next((s for s in list_sources() if s.id == identifier), None)
    return match_screen(source, QApplication.screens()) if source else None


def match_screen(source, screens):
    for screen in screens:
        geometry = screen.geometry()
        ratio = screen.devicePixelRatio()
        if (geometry.x(), geometry.y(), round(geometry.width() * ratio),
                round(geometry.height() * ratio)) == (source.left, source.top, source.width, source.height):
            return screen
    return None


class OutputWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("HDR Screen Share")
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        # Keep normal application-list eligibility. NOACTIVATE also hides the
        # output from taskbar-style pickers; this attribute only avoids focus on show.
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.image = QImage()
        self._pixels = None
        self.output_size = (1280, 720)
        self.presented = 0
        self.received = 0
        self._painted_sequence = 0
        self.target_screen = None
        self.resize(1280, 720)

    def place_on(self, screen):
        self.target_screen = screen
        self.winId()
        self.windowHandle().setScreen(screen)
        self.move(screen.geometry().topLeft())

    def set_frame(self, frame: np.ndarray):
        # LatestFrame hands over an owned array. Keep it alive for QImage's entire lifetime.
        self._pixels = frame
        height, width, _ = frame.shape
        self.image = QImage(frame.data, width, height, frame.strides[0],
                            QImage.Format.Format_ARGB32)
        self.image.setColorSpace(QColorSpace(QColorSpace.NamedColorSpace.SRgb))
        self.output_size = fit_size(width, height)
        ratio = self.devicePixelRatioF()
        if self.target_screen:
            geometry = self.target_screen.geometry()
            self.output_size = output_dimensions(width, height, round(geometry.width() * ratio),
                                                 round(geometry.height() * ratio))
        logical = (max(1, round(self.output_size[0] / ratio)),
                   max(1, round(self.output_size[1] / ratio)))
        if (self.width(), self.height()) != logical:
            self.setFixedSize(*logical)
            if self.target_screen:
                self.move(self.target_screen.geometry().topLeft())
        self.received += 1
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("black"))
        if not self.image.isNull():
            painter.drawImage(self.rect(), self.image)
            if self.received != self._painted_sequence:
                self.presented += 1
                self._painted_sequence = self.received

    def closeEvent(self, event):
        event.accept()


def exclude_control_from_capture(hwnd):
    import ctypes as C
    from ctypes import wintypes as W
    api = C.WinDLL("user32", use_last_error=True)
    api.SetWindowDisplayAffinity.argtypes = [W.HWND, W.DWORD]
    api.SetWindowDisplayAffinity.restype = W.BOOL
    return bool(api.SetWindowDisplayAffinity(hwnd, 0x11))


class PreviewWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(480, 270)
        self.image = QImage()
        self.received = 0

    def set_frame(self, pixels):
        height, width, _ = pixels.shape
        image = QImage(pixels.data, width, height, pixels.strides[0], QImage.Format.Format_ARGB32)
        self.image = image.scaled(self.width(), self.height(), Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.FastTransformation).copy()
        self.received += 1
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#0b1018"))
        if self.image.isNull():
            painter.setPen(QColor("#74849c"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Preview")
        else:
            x, y = (self.width() - self.image.width()) // 2, (self.height() - self.image.height()) // 2
            painter.drawImage(x, y, self.image)


class ControlWindow(QWidget):
    closed = Signal()

    def __init__(self, *, sources=list_sources, worker_factory=CaptureWorker,
                 screen_lookup=screen_for_source, autostart=False, controller=None,
                 owned_display=None, affinity=exclude_control_from_capture, default_mode="screen"):
        super().__init__()
        from .stream import StreamController
        from .virtual_display import WindowsDisplayBackend
        self._sources, self._screen_lookup = sources, screen_lookup
        self._owned_display = owned_display or WindowsDisplayBackend().owned_display
        self._affinity = affinity
        self._affinity_set = False
        self._preview_allowed = True
        self.controller = controller or StreamController(sources=sources, worker_factory=worker_factory,
                                                        screen_lookup=screen_lookup)
        self.output = self.controller.output
        self._preview_sequence = 0
        self._before_sequence = 0
        self._last_counts = (0, 0)
        self._last_stats_at = time.monotonic()
        self._verify_at = 0
        self._watched_screens = []
        self.setWindowTitle("HDR Screen Share — Controls")
        self.setFixedWidth(528)
        self.setStyleSheet("""
            QWidget { background: #141923; color: #edf2fc; font-family: 'Segoe UI'; font-size: 13px; }
            QLabel#title { font-size: 25px; font-weight: 650; }
            QLabel#hint { color: #aab8ce; }
            QComboBox { padding: 9px; background: #202a3b; border: 1px solid #39465c; border-radius: 6px; }
            QPushButton { padding: 9px 13px; background: #324766; border: 0; border-radius: 6px; }
            QPushButton:hover { background: #425d84; }
            QPushButton#start { background: #5265dc; }
            QPushButton:disabled { color: #7d899b; background: #252c39; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        title = QLabel("HDR → SDR")
        title.setObjectName("title")
        layout.addWidget(title)
        hint = QLabel("HDR screen to SDR for Discord.")
        hint.setObjectName("hint")
        layout.addWidget(hint)
        self.monitors = QComboBox()
        layout.addWidget(self.monitors)
        self.share_mode = QComboBox()
        self.share_mode.addItem("Virtual screen", "screen")
        self.share_mode.addItem("Application window", "application")
        self.share_mode.setCurrentIndex(self.share_mode.findData(default_mode))
        layout.addWidget(self.share_mode)
        self.compare_toggle = QCheckBox('Before / After')
        layout.addWidget(self.compare_toggle)
        previews = QHBoxLayout()
        previews.setSpacing(8)
        self.before_panel = QWidget()
        before_layout = QVBoxLayout(self.before_panel)
        before_layout.setContentsMargins(0, 0, 0, 0)
        before_layout.addWidget(QLabel('Before · Unmapped'))
        self.before_preview = PreviewWidget()
        self.before_preview.setFixedSize(236, 133)
        before_layout.addWidget(self.before_preview)
        self.before_panel.hide()
        previews.addWidget(self.before_panel)
        after_panel = QWidget()
        after_layout = QVBoxLayout(after_panel)
        after_layout.setContentsMargins(0, 0, 0, 0)
        self.after_label = QLabel('After · SDR')
        self.after_label.hide()
        after_layout.addWidget(self.after_label)
        self.preview = PreviewWidget()
        after_layout.addWidget(self.preview)
        previews.addWidget(after_panel)
        layout.addLayout(previews)
        buttons = QHBoxLayout()
        self.start_button = QPushButton("Start")
        self.start_button.setObjectName("start")
        self.stop_button = QPushButton("Stop")
        self.refresh_button = QPushButton("Refresh")
        for button in (self.start_button, self.stop_button, self.refresh_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.status = QLabel("Ready")
        self.audio_status = QLabel("Audio: off")
        self.display_status = QLabel('Display: off')
        self.comparison_status = QLabel('Comparison: off')
        self.comparison_status.hide()
        self.device_status = QLabel("")
        for label in (self.status, self.audio_status, self.display_status,
                      self.comparison_status, self.device_status):
            label.setWordWrap(True)
            layout.addWidget(label)
        self.device_status.hide()
        self.stats = QLabel("Up to 4K · 60 FPS target")
        self.stats.setObjectName("hint")
        layout.addWidget(self.stats)
        self.instruction = QLabel("")
        self.instruction.setWordWrap(True)
        self.instruction.setObjectName("hint")
        layout.addWidget(self.instruction)
        self.devices_button = QPushButton("Devices")
        layout.addWidget(self.devices_button)
        self.start_button.clicked.connect(self.start_capture)
        self.stop_button.clicked.connect(self.stop_capture)
        self.refresh_button.clicked.connect(self.refresh_sources)
        self.devices_button.clicked.connect(self.show_devices)
        self.monitors.currentIndexChanged.connect(self.change_source)
        self.share_mode.currentIndexChanged.connect(self.change_mode)
        self.compare_toggle.toggled.connect(self.change_comparison)
        self.controller.changed.connect(self.sync_state)
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(4)
        self.timer.timeout.connect(self.present_latest)
        self.preview_timer = QTimer(self)
        self.preview_timer.setInterval(67)
        self.preview_timer.timeout.connect(self.present_preview)
        self.preview_timer.start()
        app = QApplication.instance()
        app.screenRemoved.connect(self.display_changed)
        app.screenAdded.connect(self.display_changed)
        self.refresh_sources()
        if autostart:
            QTimer.singleShot(0, self.start_capture)

    @property
    def worker(self): return self.controller.worker

    @property
    def frames(self): return self.controller.frames

    @property
    def _running(self): return self.controller.running

    def sync_state(self):
        self.status.setText(f'Video: {self.controller.video_status}')
        self.update_instruction()
        self.audio_status.setText(self.controller.audio_status)
        self.display_status.setText(self.controller.display_status)
        self.start_button.setEnabled(not self._running and self.monitors.count() > 0)
        self.stop_button.setEnabled(self._running or self.worker is not None or self.controller.lease is not None)
        if not self._running:
            self.timer.stop()
            self.clear_previews()

    def clear_previews(self):
        for preview in (self.preview, self.before_preview):
            preview.image = QImage()
            preview.update()
        self.comparison_status.setText('Comparison: off')
        self.stats.setText('Up to 4K · 60 FPS target')

    def change_comparison(self, enabled):
        self.before_panel.setVisible(enabled)
        self.after_label.setVisible(enabled)
        self.comparison_status.setVisible(enabled)
        self.preview.setFixedSize(236, 133) if enabled else self.preview.setFixedSize(480, 270)
        self._preview_sequence = self._before_sequence = 0
        self.before_preview.image = QImage()
        self.before_preview.update()
        self.comparison_status.setText('Comparison: waiting for Start' if enabled else 'Comparison: off')
        if self.worker is not None:
            self.worker.set_comparison_enabled(enabled and self._preview_allowed and not self.isMinimized())
        self.adjustSize()

    def refresh_sources(self):
        if not self.stop_capture():
            return
        previous = self.monitors.currentData()
        try:
            owned = self._owned_display()
            self.sources = [source for source in self._sources() if source.id != owned]
            for screen in QApplication.screens():
                if screen not in self._watched_screens:
                    screen.geometryChanged.connect(self.display_changed)
                    screen.logicalDotsPerInchChanged.connect(self.display_changed)
                    self._watched_screens.append(screen)
            selected = next((s for s in self.sources if s.id == previous), None) or default_source(self.sources)
            self.monitors.blockSignals(True)
            self.monitors.clear()
            for source in self.sources:
                hdr = "HDR" if source.hdr_enabled is True else "SDR" if source.hdr_enabled is False else "Unknown"
                screen = self._screen_lookup(source.id)
                name = screen.name() if screen else source.label
                self.monitors.addItem(f"{name} · {source.width}×{source.height} · {hdr}", source.id)
            self.monitors.setCurrentIndex(self.monitors.findData(selected.id))
            self.controller.video_status = "Ready"
        except Exception as error:
            self.controller.video_status = f"Error: {error}"
        finally:
            self.monitors.blockSignals(False)
            self.sync_state()

    def update_instruction(self):
        if self.share_mode.currentData() == "screen":
            number = getattr(self.controller, "target_number", None) if self._running else None
            target = f"Screen {number}" if number else "the virtual screen"
            self.instruction.setText(f"Discord: share {target} · System audio on")
        else:
            self.instruction.setText("Discord: share HDR Screen Share · App audio on")

    def change_mode(self):
        self.update_instruction()
        if self._running:
            self.start_capture()

    def change_source(self):
        if self._running:
            self.start_capture()

    def start_capture(self):
        source_id = self.monitors.currentData()
        if source_id is None:
            return
        self._preview_sequence = 0
        self._before_sequence = 0
        self._last_counts = (0, self.output.presented)
        self._last_stats_at = time.monotonic()
        self._verify_at = time.monotonic() + 1
        self.controller.start(source_id, mode=self.share_mode.currentData())
        if self._running:
            self.worker.set_comparison_enabled(self.compare_toggle.isChecked() and self._preview_allowed
                                               and not self.isMinimized())
            self.timer.start()
        self.sync_state()

    def stop_capture(self):
        result = self.controller.stop()
        self.sync_state()
        return result

    def display_changed(self, *args):
        self.controller.display_changed(*args)

    def verify_displays(self):
        self.controller.verify_displays()
        self.sync_state()

    def present_preview(self):
        compare = self.compare_toggle.isChecked()
        if self.worker is not None:
            self.worker.set_comparison_enabled(compare and self._preview_allowed and not self.isMinimized())
        if not self._running or self.isMinimized() or not self._preview_allowed:
            return
        item = self.frames.latest_after(self._preview_sequence)
        if item is not None:
            self._preview_sequence, pixels, _ = item
            self.preview.set_frame(pixels)
        if compare and self.worker is not None:
            self.comparison_status.setText(f'Comparison: {self.worker.comparison_status}')
            item = self.worker.comparison_frames.latest_after(self._before_sequence)
            if item is not None:
                self._before_sequence, pixels, _ = item
                self.before_preview.set_frame(pixels)
            elif self.worker.comparison_status != 'Live':
                self.before_preview.image = QImage()
                self.before_preview.update()

    def present_latest(self):
        self.controller.present_latest()
        now = time.monotonic()
        if now >= self._verify_at:
            self._verify_at = now + 1
            self.verify_displays()
        worker = self.worker
        if worker and now - self._last_stats_at >= 1:
            seconds = now - self._last_stats_at
            captured = (worker.captured - self._last_counts[0]) / seconds
            painted = (self.output.presented - self._last_counts[1]) / seconds
            width, height = self.output.output_size
            self.stats.setText(f"{width}×{height} · {painted:.0f} FPS")
            self._last_counts = (worker.captured, self.output.presented)
            self._last_stats_at = now

    def show_devices(self):
        from .device_setup import DeviceSetupDialog
        box = DeviceSetupDialog(self, before_install=self.stop_capture, mode=self.share_mode.currentData())
        box.exec()

    def showEvent(self, event):
        super().showEvent(event)
        if not self._affinity_set:
            self._affinity_set = True
            self._preview_allowed = self._affinity(int(self.winId()))
            if not self._preview_allowed:
                self.device_status.setText("Preview unavailable")
                self.device_status.show()

    def closeEvent(self, event):
        if self.stop_capture():
            self.preview_timer.stop()
            self.output.close()
            event.accept()
            self.closed.emit()
        else:
            event.ignore()
