"""docker-py 래퍼: 컨테이너 발견·상태·수명주기·exec.

UI/Qt를 모른다. SERVER_ID로만 다룬다. compose 서비스 라벨(agent-N)로 컨테이너를
발견해 매핑한다. 모든 호출은 블로킹이므로 호출 측(poller)이 워커 스레드에서 부른다.
"""

import threading

import docker

from app import config


class DockerControl:
    def __init__(self, client=None) -> None:
        # client 주입은 테스트용. 실제 실행은 from_env로 도커 소켓에 붙는다.
        self._client = client or docker.from_env()
        self._by_id: dict[int, object] = {}
        self._lock = threading.Lock()

    def discover(self) -> dict[int, object]:
        """실행/정지 포함 모든 컨테이너에서 agent-N을 찾아 SERVER_ID로 매핑한다."""
        found: dict[int, object] = {}
        for container in self._client.containers.list(all=True):
            service = container.labels.get(config.COMPOSE_SERVICE_LABEL, "")
            server_id = config.service_to_server_id(service)
            if server_id is not None:
                found[server_id] = container
        with self._lock:
            self._by_id = found
        return found

    def _get(self, server_id: int):
        with self._lock:
            return self._by_id.get(server_id)

    def status(self, server_id: int) -> str:
        """컨테이너 상태 문자열. 발견 안 됐으면 'offline'."""
        container = self._get(server_id)
        if container is None:
            return "offline"
        container.reload()
        return container.status

    def start(self, server_id: int) -> None:
        container = self._get(server_id)
        if container is not None:
            container.start()

    def stop(self, server_id: int) -> None:
        container = self._get(server_id)
        if container is not None:
            container.stop()

    def restart(self, server_id: int) -> None:
        container = self._get(server_id)
        if container is not None:
            container.restart()

    def exec_run(self, server_id: int, cmd: list[str]):
        container = self._get(server_id)
        if container is not None:
            return container.exec_run(cmd)
        return None

    def exec_detached(self, server_id: int, cmd: list[str]) -> None:
        container = self._get(server_id)
        if container is not None:
            container.exec_run(cmd, detach=True)
