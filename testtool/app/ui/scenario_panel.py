"""카오스 시나리오 선택·파라미터·시작/중지."""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QPushButton, QSpinBox, QVBoxLayout,
)

SCENARIOS = ["전체 과부하", "랜덤 정지", "랜덤 부하 스파이크"]


class ScenarioPanel(QGroupBox):
    startRequested = pyqtSignal(dict)  # {scenario, duration_min, stop_min, stop_max, intensity}
    stopRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("카오스 시나리오", parent)
        self._combo = QComboBox()
        self._combo.addItems(SCENARIOS)
        self._duration = self._spin(1, 120, 5)
        self._stop_min = self._spin(1, 600, 10)
        self._stop_max = self._spin(1, 600, 60)
        self._intensity = self._spin(10, 100, 80)
        form = QFormLayout()
        form.addRow("시나리오", self._combo)
        form.addRow("지속(분)", self._duration)
        form.addRow("정지 최소(초)", self._stop_min)
        form.addRow("정지 최대(초)", self._stop_max)
        form.addRow("강도(%)", self._intensity)
        buttons = QHBoxLayout()
        start_btn = QPushButton("▶ 시작")
        stop_btn = QPushButton("■ 중지")
        start_btn.clicked.connect(self._emit_start)
        stop_btn.clicked.connect(self.stopRequested)
        buttons.addWidget(start_btn)
        buttons.addWidget(stop_btn)
        outer = QVBoxLayout(self)
        outer.addLayout(form)
        outer.addLayout(buttons)

    @staticmethod
    def _spin(low, high, default):
        s = QSpinBox()
        s.setRange(low, high)
        s.setValue(default)
        return s

    def _emit_start(self):
        self.startRequested.emit(
            {
                "scenario": self._combo.currentText(),
                "duration_min": self._duration.value(),
                "stop_min": self._stop_min.value(),
                "stop_max": self._stop_max.value(),
                "intensity": self._intensity.value(),
            }
        )
