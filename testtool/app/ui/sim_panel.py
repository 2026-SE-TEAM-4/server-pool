"""선택 서버의 모드 토글·자원별 기준선(시드) 제어.

시그널만 낸다. modeRequested(server_id, mode), baselineRequested(server_id, resource,
value(None=해제/int=적용)). 실행은 main_window가 워커로 디스패치한다.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton,
    QRadioButton, QSlider, QVBoxLayout, QWidget,
)

_MODES = [("stable", "안정 합성"), ("real", "psutil 실측"), ("randomwalk", "랜덤워크")]
_RESOURCES = [("cpu", "CPU"), ("ram", "RAM"), ("gpu", "GPU"), ("net", "Net")]


class SimPanel(QGroupBox):
    modeRequested = pyqtSignal(int, str)          # server_id, mode
    baselineRequested = pyqtSignal(int, str, object)  # server_id, resource, value(None/int)

    def __init__(self, parent=None):
        super().__init__("모드 · 기준선(시드)", parent)
        self._server_id: int | None = None
        self._title = QLabel("서버를 선택하세요")

        mode_row = QHBoxLayout()
        self._mode_group = QButtonGroup(self)
        for key, label in _MODES:
            rb = QRadioButton(label)
            rb.toggled.connect(lambda on, k=key: self._on_mode(k) if on else None)
            self._mode_group.addButton(rb)
            mode_row.addWidget(rb)

        grid = QGridLayout()
        self._sliders: dict[str, QSlider] = {}
        for r, (res, label) in enumerate(_RESOURCES):
            grid.addWidget(QLabel(label), r, 0)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 100)
            slider.setValue(50)
            self._sliders[res] = slider
            grid.addWidget(slider, r, 1)
            apply_btn = QPushButton("적용")
            clear_btn = QPushButton("해제")
            apply_btn.clicked.connect(lambda _, rs=res: self._apply(rs))
            clear_btn.clicked.connect(lambda _, rs=res: self._clear(rs))
            grid.addWidget(apply_btn, r, 2)
            grid.addWidget(clear_btn, r, 3)

        wrap = QWidget()
        wrap.setLayout(grid)
        outer = QVBoxLayout(self)
        outer.addWidget(self._title)
        outer.addWidget(QLabel("모드"))
        outer.addLayout(mode_row)
        outer.addWidget(QLabel("자원별 기준선 %"))
        outer.addWidget(wrap)

    def set_server(self, server_id: int):
        self._server_id = server_id
        self._title.setText(f"#{server_id} 시뮬레이션")

    def _on_mode(self, mode: str):
        if self._server_id is not None:
            self.modeRequested.emit(self._server_id, mode)

    def _apply(self, resource: str):
        if self._server_id is not None:
            self.baselineRequested.emit(self._server_id, resource, self._sliders[resource].value())

    def _clear(self, resource: str):
        if self._server_id is not None:
            self.baselineRequested.emit(self._server_id, resource, None)
