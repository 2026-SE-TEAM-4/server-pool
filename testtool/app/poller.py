"""백그라운드 폴러: QThreadPool에서 docker 상태 + 에이전트 메트릭을 모아 시그널로 전달.

블로킹 호출(docker.reload, httpx.get)을 UI 스레드에서 떼어내 GUI 프리징을 막는다.
QTimer가 주기마다 워커를 풀에 제출하고, 워커는 끝나면 snapshotReady를 emit한다.
"""

from dataclasses import dataclass

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, QTimer, pyqtSignal

from app import agent_client, config
from app.docker_control import DockerControl


@dataclass
class ServerSnapshot:
    server_id: int
    status: str
    metrics: agent_client.AgentMetrics


class _Signals(QObject):
    done = pyqtSignal(list)  # list[ServerSnapshot]


class _PollJob(QRunnable):
    def __init__(self, docker: DockerControl):
        super().__init__()
        self._docker = docker
        self.signals = _Signals()

    def run(self):
        self._docker.discover()
        snapshots = []
        for sid in config.SERVER_IDS:
            status = self._docker.status(sid)
            metrics = (
                agent_client.fetch_for(sid)
                if status == "running"
                else agent_client.AgentMetrics(online=False)
            )
            snapshots.append(ServerSnapshot(sid, status, metrics))
        self.signals.done.emit(snapshots)


class Poller(QObject):
    snapshotReady = pyqtSignal(list)

    def __init__(self, docker: DockerControl, parent=None):
        super().__init__(parent)
        self._docker = docker
        self._pool = QThreadPool.globalInstance()
        self._timer = QTimer(self)
        self._timer.setInterval(config.POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._submit)

    def start(self):
        self._submit()
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def _submit(self):
        job = _PollJob(self._docker)
        job.signals.done.connect(self.snapshotReady)
        self._pool.start(job)
