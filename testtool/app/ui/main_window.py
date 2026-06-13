"""전체 조립: 폴러 → 테이블, 패널 시그널 → 액션 디스패치, 시나리오 → 러너."""

import random

from PyQt6.QtCore import QRunnable, QThreadPool, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from app import config, scenarios
from app.docker_control import DockerControl
from app.load_injector import LoadInjector
from app.poller import Poller
from app.ui.log_panel import LogPanel
from app.ui.scenario_panel import ScenarioPanel
from app.ui.server_panel import ServerPanel
from app.ui.server_table import ServerTable


class _Task(QRunnable):
    def __init__(self, fn, on_error):
        super().__init__()
        self._fn = fn
        self._on_error = on_error

    def run(self):
        try:
            self._fn()
        except Exception as exc:
            self._on_error(str(exc))


class MainWindow(QWidget):
    actionError = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("server-pool 테스트 콘솔")
        self.resize(900, 700)
        self._pool = QThreadPool.globalInstance()
        self._docker = DockerControl()
        self._injector = LoadInjector(self._docker)
        self._runner = None
        self._last_running: set[int] = set()

        self._table = ServerTable(config.SERVER_IDS)
        self._panel = ServerPanel()
        self._scenario = ScenarioPanel()
        self._log = LogPanel()
        self._poller = Poller(self._docker)

        left = QVBoxLayout()
        left.addWidget(self._table)
        left.addWidget(self._panel)
        right = QVBoxLayout()
        right.addWidget(self._scenario)
        right.addWidget(self._log)
        root = QHBoxLayout(self)
        root.addLayout(left, 2)
        root.addLayout(right, 1)

        self._table.serverSelected.connect(self._panel.set_server)
        self._panel.metricRequested.connect(self._on_metric)
        self._panel.lifecycleRequested.connect(self._on_lifecycle)
        self._scenario.startRequested.connect(self._on_scenario_start)
        self._scenario.stopRequested.connect(self._on_scenario_stop)
        self._poller.snapshotReady.connect(self._on_snapshot)
        self.actionError.connect(self._log.append)
        self._poller.start()

    def _run_async(self, fn):
        self._pool.start(_Task(fn, self.actionError.emit))

    def _on_snapshot(self, snapshots):
        self._table.update_snapshots(snapshots)
        self._last_running = {s.server_id for s in snapshots if s.status == "running"}
        if self._runner is not None:
            self._runner.set_running(self._last_running)

    def _on_metric(self, server_id, resource, value):
        inj = self._injector
        if resource == "cpu":
            fn = (lambda: inj.clear_cpu(server_id)) if value is None else (lambda: inj.apply_cpu(server_id, value))
        elif resource == "ram":
            fn = (lambda: inj.clear_ram(server_id)) if value is None else (lambda: inj.apply_ram(server_id, value))
        else:  # gpu
            fn = (lambda: inj.clear_gpu(server_id)) if value is None else (lambda: inj.set_gpu(server_id, value))
        self._run_async(fn)
        label = "되돌리기" if value is None else f"{value}%"
        self._log.append(f"agent-{server_id} {resource.upper()} {label}")

    def _on_lifecycle(self, server_id, action):
        fn = (lambda: self._docker.stop(server_id)) if action == "stop" else (lambda: self._docker.restart(server_id))
        self._run_async(fn)
        self._log.append(f"agent-{server_id} {'정지' if action == 'stop' else '재시작'}")

    def _on_scenario_start(self, params):
        engine = self._build_engine(params)
        self._runner = scenarios.ChaosRunner(
            engine, self._docker, self._injector, random.Random(), parent=self
        )
        self._runner.set_running(self._last_running)
        self._runner.log.connect(self._log.append)
        self._runner.start()
        self._log.append(f"카오스 시작: {params['scenario']}")

    def _on_scenario_stop(self):
        if self._runner is not None:
            self._runner.stop()
            self._runner = None

    def _build_engine(self, p):
        ids = config.SERVER_IDS
        duration_s = p["duration_min"] * 60
        if p["scenario"] == "전체 과부하":
            return scenarios.OverloadAll(ids, p["intensity"], duration_s)
        if p["scenario"] == "랜덤 정지":
            return scenarios.RandomStop(ids, duration_s, p["stop_min"], p["stop_max"], every_s=5)
        return scenarios.RandomSpike(ids, duration_s, every_s=5)
