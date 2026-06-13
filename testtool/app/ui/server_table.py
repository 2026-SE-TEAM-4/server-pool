"""서버 리스트 테이블. 폴러 스냅샷으로 갱신, 선택 시 server_id 시그널."""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem, QAbstractItemView

_COLS = ["ID", "상태", "CPU", "RAM", "GPU", "Net"]


def _fmt(value):
    return "-" if value is None else f"{value:.0f}%"


class ServerTable(QTableWidget):
    serverSelected = pyqtSignal(int)

    def __init__(self, server_ids, parent=None):
        super().__init__(len(server_ids), len(_COLS), parent)
        self._ids = list(server_ids)
        self.setHorizontalHeaderLabels(_COLS)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.verticalHeader().setVisible(False)
        for row, sid in enumerate(self._ids):
            self.setItem(row, 0, QTableWidgetItem(str(sid)))
        self.itemSelectionChanged.connect(self._on_select)

    def _on_select(self):
        rows = self.selectionModel().selectedRows()
        if rows:
            self.serverSelected.emit(self._ids[rows[0].row()])

    def update_snapshots(self, snapshots):
        by_id = {s.server_id: s for s in snapshots}
        for row, sid in enumerate(self._ids):
            snap = by_id.get(sid)
            if snap is None:
                continue
            m = snap.metrics
            values = [snap.status, _fmt(m.cpu), _fmt(m.mem), _fmt(m.gpu), _fmt(m.net)]
            for col, text in enumerate(values, start=1):
                self.setItem(row, col, QTableWidgetItem(text))
