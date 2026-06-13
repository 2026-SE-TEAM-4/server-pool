"""선택 서버 제어: CPU/RAM/GPU 되돌리기/50/100, 정지/재시작.

위젯은 시그널만 낸다(action, server_id, resource, value). 실제 실행은 main_window가
워커로 디스패치한다. resource: cpu|ram|gpu, value: None(되돌리기)|50|100.
"""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)


class ServerPanel(QGroupBox):
    metricRequested = pyqtSignal(int, str, object)  # server_id, resource, value(None/50/100)
    lifecycleRequested = pyqtSignal(int, str)       # server_id, "stop"|"restart"

    def __init__(self, parent=None):
        super().__init__("선택 서버 제어", parent)
        self._server_id: int | None = None
        self._title = QLabel("서버를 선택하세요")
        grid = QGridLayout()
        for r, (res, label) in enumerate([("cpu", "CPU"), ("ram", "RAM"), ("gpu", "GPU")]):
            grid.addWidget(QLabel(label), r, 0)
            for c, (text, value) in enumerate(
                [("되돌리기", None), ("50%", 50), ("100%", 100)], start=1
            ):
                btn = QPushButton(text)
                btn.clicked.connect(
                    lambda _, rs=res, v=value: self._emit_metric(rs, v)
                )
                grid.addWidget(btn, r, c)
        life = QHBoxLayout()
        stop_btn = QPushButton("■ 정지")
        restart_btn = QPushButton("↻ 재시작")
        stop_btn.clicked.connect(lambda: self._emit_life("stop"))
        restart_btn.clicked.connect(lambda: self._emit_life("restart"))
        life.addWidget(stop_btn)
        life.addWidget(restart_btn)
        outer = QVBoxLayout(self)
        outer.addWidget(self._title)
        wrap = QWidget()
        wrap.setLayout(grid)
        outer.addWidget(wrap)
        outer.addLayout(life)

    def set_server(self, server_id: int):
        self._server_id = server_id
        self._title.setText(f"#{server_id} 제어")

    def _emit_metric(self, resource, value):
        if self._server_id is not None:
            self.metricRequested.emit(self._server_id, resource, value)

    def _emit_life(self, action):
        if self._server_id is not None:
            self.lifecycleRequested.emit(self._server_id, action)
