import time

import numpy as np
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPainter, QColor, QColorSpace
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                              QLabel, QComboBox, QPushButton)

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
        self.setWindowTitle("HDR Screen Share — Discord")
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
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


class ControlWindow(QWidget):
    closed = Signal()

    def __init__(self, *, sources=list_sources, worker_factory=CaptureWorker,
                 screen_lookup=screen_for_source, autostart=True):
        super().__init__()
        self._sources = sources
        self._worker_factory = worker_factory
        self._screen_lookup = screen_lookup
        self.worker = None
        self.frames = LatestFrame()
        self.output = OutputWindow()
        self._running = False
        self._failed = False
        self._last_counts = (0, 0)
        self._last_stats_at = time.monotonic()
        self._topology = ()
        self._verify_at = 0.0
        self._watched_screens = []
        self.setWindowTitle("HDR Screen Share")
        self.setMinimumWidth(490)
        self.setStyleSheet("""
            QWidget { background: #141923; color: #edf2fc; font-family: 'Segoe UI'; font-size: 13px; }
            QLabel#title { font-size: 24px; font-weight: 650; }
            QLabel#hint { color: #aab8ce; }
            QComboBox { padding: 10px; background: #202a3b; border: 1px solid #39465c; border-radius: 6px; }
            QPushButton { padding: 10px 16px; background: #324766; border: 0; border-radius: 6px; }
            QPushButton:hover { background: #425d84; }
            QPushButton#start { background: #5265dc; }
            QPushButton:disabled { color: #7d899b; background: #252c39; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        title = QLabel("HDR → SDR")
        title.setObjectName("title")
        layout.addWidget(title)
        hint = QLabel("Нормальная яркость для зрителей Discord")
        hint.setObjectName("hint")
        layout.addWidget(hint)
        layout.addWidget(QLabel("Монитор для трансляции"))
        self.monitors = QComboBox()
        layout.addWidget(self.monitors)
        layout.addWidget(QLabel("Второй монитор — окно для Discord"))
        self.outputs = QComboBox()
        layout.addWidget(self.outputs)
        buttons = QHBoxLayout()
        self.start_button = QPushButton("Запустить")
        self.start_button.setObjectName("start")
        self.stop_button = QPushButton("Остановить")
        self.refresh_button = QPushButton("Обновить")
        for button in (self.start_button, self.stop_button, self.refresh_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.status = QLabel("Готово к запуску")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.stats = QLabel("До 4K · цель 60 FPS")
        self.stats.setObjectName("hint")
        layout.addWidget(self.stats)
        instruction = QLabel("В Discord выберите трансляцию приложения:\n"
                             "HDR Screen Share — Discord\n\n"
                             "Окно-копия открывается на втором мониторе.\n"
                             "Его можно перекрывать окнами, но нельзя сворачивать.\n"
                             "Звук игры эта версия не передаёт.")
        instruction.setObjectName("hint")
        instruction.setWordWrap(True)
        layout.addWidget(instruction)
        self.start_button.clicked.connect(self.start_capture)
        self.stop_button.clicked.connect(self.stop_capture)
        self.refresh_button.clicked.connect(self.refresh_sources)
        self.monitors.currentIndexChanged.connect(self.change_source)
        self.outputs.currentIndexChanged.connect(self.change_output)
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(4)
        self.timer.timeout.connect(self.present_latest)
        app = QApplication.instance()
        app.screenRemoved.connect(self.display_changed)
        app.screenAdded.connect(self.display_changed)
        self.refresh_sources()
        self.stop_button.setEnabled(False)
        if autostart:
            QTimer.singleShot(0, self.start_capture)

    def refresh_sources(self):
        if not self.stop_capture():
            return
        previous = self.monitors.currentData()
        try:
            self.sources = self._sources()
            for screen in QApplication.screens():
                if screen not in self._watched_screens:
                    screen.geometryChanged.connect(self.display_changed)
                    screen.logicalDotsPerInchChanged.connect(self.display_changed)
                    self._watched_screens.append(screen)
            selected = next((s for s in self.sources if s.id == previous), None) or default_source(self.sources)
            self.monitors.blockSignals(True)
            self.monitors.clear()
            for number, source in enumerate(self.sources, 1):
                hdr = "HDR включён" if source.hdr_enabled is True else "SDR" if source.hdr_enabled is False else "HDR неизвестен"
                primary = " · основной" if source.primary else ""
                screen = self._screen_lookup(source.id)
                name = screen.name() if screen else source.label
                self.monitors.addItem(f"{name} · {source.width}×{source.height} · {hdr}{primary}", source.id)
            self.monitors.setCurrentIndex(self.monitors.findData(selected.id))
            self.populate_outputs()
            self.start_button.setEnabled(True)
            self.status.setText("Выберите монитор и запустите захват")
        except Exception as exc:
            self.status.setText(f"Ошибка: {exc}")
            self.start_button.setEnabled(False)
        finally:
            self.monitors.blockSignals(False)

    def change_source(self):
        self.populate_outputs()
        if self._running:
            self.start_capture()

    def populate_outputs(self):
        previous = self.outputs.currentData()
        selected = choose_output([s.id for s in self.sources], self.monitors.currentData(), previous)
        self.outputs.blockSignals(True)
        self.outputs.clear()
        for number, source in enumerate(self.sources, 1):
            if source.id != self.monitors.currentData():
                screen = self._screen_lookup(source.id)
                name = screen.name() if screen else source.label
                self.outputs.addItem(f"{name} · {source.width}×{source.height}", source.id)
        self.outputs.setCurrentIndex(self.outputs.findData(selected))
        self.outputs.blockSignals(False)

    def change_output(self):
        if self._running:
            self.start_capture()

    def start_capture(self):
        if not self.stop_capture():
            return
        source_id = self.monitors.currentData()
        if source_id is None:
            return
        target_id = self.outputs.currentData()
        screen = self._screen_lookup(target_id) if target_id else None
        if screen is None:
            self.status.setText("Для окна Discord нужен второй подключённый монитор. Обновите список.")
            return
        self.frames = LatestFrame()
        try:
            self._topology = self.topology(self._sources(), source_id, target_id)
        except Exception as exc:
            self.status.setText(f"Конфигурация мониторов недоступна: {exc}")
            return
        self._verify_at = time.monotonic() + 1
        worker = self._worker_factory(source_id, self.frames)
        self.worker = worker
        self._running = True
        self._failed = False
        self._last_counts = (0, self.output.presented)
        self._last_stats_at = time.monotonic()
        worker.ready.connect(lambda hdr: self.on_ready(worker, hdr))
        worker.failed.connect(lambda error: self.on_error(worker, error))
        worker.finished.connect(lambda: self.on_finished(worker))
        self.status.setText("Запуск захвата…")
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.output.place_on(screen)
        self.output.show()
        self.timer.start()
        worker.start()

    def on_ready(self, worker, hdr):
        if worker is self.worker and self._running:
            self.status.setText("HDR → SDR · захват работает" if hdr else "SDR · HDR на этом мониторе выключен")

    def on_error(self, worker, message):
        if worker is self.worker:
            self._failed = True
            self.status.setText(f"Ошибка захвата: {message}")

    def on_finished(self, worker):
        if worker is self.worker:
            self._running = False
            self.timer.stop()
            self.output.hide()
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)

    def stop_capture(self):
        worker = self.worker
        if worker is not None:
            worker.request_stop()
            if not worker.wait(3000):
                self.status.setText("Ожидание остановки захвата… Повторите через несколько секунд.")
                return False
            self.worker = None
            worker.deleteLater()
        self._running = False
        self.timer.stop()
        self.frames.take()
        self.output.hide()
        self.start_button.setEnabled(self.monitors.count() > 0)
        self.stop_button.setEnabled(False)
        if not self._failed:
            self.status.setText("Захват остановлен")
        return True

    @staticmethod
    def topology(sources, source_id, target_id):
        selected = {s.id: s for s in sources if s.id in (source_id, target_id)}
        if source_id == target_id or len(selected) != 2:
            raise RuntimeError("Нужны два разных подключённых монитора")
        return tuple((s.id, s.index, s.left, s.top, s.width, s.height, s.hdr_enabled)
                     for s in sorted(selected.values(), key=lambda s: s.id))

    def display_changed(self, *args):
        if self._running:
            # Hide first: Windows may migrate an orphaned window onto the captured display.
            self.output.hide()
            self.stop_capture()
            self.status.setText("Конфигурация мониторов изменилась. Нажмите «Обновить» и запустите снова.")

    def verify_displays(self):
        if not self._running:
            return
        try:
            current = self.topology(self._sources(), self.monitors.currentData(), self.outputs.currentData())
            if current != self._topology:
                self.display_changed()
        except Exception:
            self.display_changed()

    def present_latest(self):
        now = time.monotonic()
        if now >= self._verify_at:
            self._verify_at = now + 1
            self.verify_displays()
            if not self._running:
                return
        frame = self.frames.take()
        if frame is not None:
            self.output.set_frame(frame)
        worker = self.worker
        now = time.monotonic()
        if worker and now - self._last_stats_at >= 1:
            seconds = now - self._last_stats_at
            captured = (worker.captured - self._last_counts[0]) / seconds
            painted = (self.output.presented - self._last_counts[1]) / seconds
            width, height = self.output.output_size
            self.stats.setText(f"{width}×{height} · захват {captured:.1f} FPS · отрисовка {painted:.1f} FPS")
            if worker.frame_size != (0, 0) and worker.frame_size != self.output.output_size:
                self.stats.setText(self.stats.text() + "\nРазмер вывода ограничен вторым монитором / пределом 4K")
            self._last_counts = (worker.captured, self.output.presented)
            self._last_stats_at = now
            if worker.last_frame_at and now - worker.last_frame_at > 3:
                self.stats.setText(self.stats.text() + " · нет новых кадров / статичный экран")

    def closeEvent(self, event):
        if self.stop_capture():
            self.output.close()
            event.accept()
            self.closed.emit()
        else:
            event.ignore()
