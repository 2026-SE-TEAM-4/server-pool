"""카오스/액션 로그 스트림."""

from PyQt6.QtWidgets import QGroupBox, QPlainTextEdit, QVBoxLayout


class LogPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("로그", parent)
        self._view = QPlainTextEdit(readOnly=True)
        self._view.setMaximumBlockCount(500)
        layout = QVBoxLayout(self)
        layout.addWidget(self._view)

    def append(self, message: str):
        self._view.appendPlainText(message)
