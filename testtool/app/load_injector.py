"""부하 주입: CPU/RAM/GPU 모두 오버라이드 파일로 통일.

에이전트 수집기는 METRIC_SIMULATE 기본 시뮬레이션 상태에서도 오버라이드 파일이
있으면 그 값을 우선한다. 테스트 툴은 docker exec로 컨테이너 안에 오버라이드 파일을
쓰거나(set) 지운다(clear). build_* 는 순수 함수라 docker 없이 테스트한다.
"""

from app import config
from app.docker_control import DockerControl


def build_set_cmd(path: str, pct: int) -> list[str]:
    """오버라이드 파일에 0~100으로 클램프한 값을 쓰는 docker exec 명령."""
    value = max(0, min(100, pct))
    return ["sh", "-c", f"echo {value} > {path}"]


def build_clear_cmd(path: str) -> list[str]:
    """오버라이드 파일을 지우는 명령(되돌리기)."""
    return ["rm", "-f", path]


class LoadInjector:
    """docker_control을 통해 오버라이드 파일을 쓰거나 지운다."""

    def __init__(self, docker: DockerControl) -> None:
        self._docker = docker

    def apply_cpu(self, server_id: int, pct: int) -> None:
        self._docker.exec_run(server_id, build_set_cmd(config.CPU_OVERRIDE_PATH, pct))

    def clear_cpu(self, server_id: int) -> None:
        self._docker.exec_run(server_id, build_clear_cmd(config.CPU_OVERRIDE_PATH))

    def apply_ram(self, server_id: int, pct: int) -> None:
        self._docker.exec_run(server_id, build_set_cmd(config.MEM_OVERRIDE_PATH, pct))

    def clear_ram(self, server_id: int) -> None:
        self._docker.exec_run(server_id, build_clear_cmd(config.MEM_OVERRIDE_PATH))

    def set_gpu(self, server_id: int, pct: int) -> None:
        self._docker.exec_run(server_id, build_set_cmd(config.GPU_OVERRIDE_PATH, pct))

    def clear_gpu(self, server_id: int) -> None:
        self._docker.exec_run(server_id, build_clear_cmd(config.GPU_OVERRIDE_PATH))

    def apply_net(self, server_id: int, pct: int) -> None:
        self._docker.exec_run(server_id, build_set_cmd(config.NET_OVERRIDE_PATH, pct))

    def clear_net(self, server_id: int) -> None:
        self._docker.exec_run(server_id, build_clear_cmd(config.NET_OVERRIDE_PATH))

    def revert_all(self, server_id: int) -> None:
        """한 서버의 CPU/RAM/GPU/Net 오버라이드를 모두 지운다. 개별 실패는 무시."""
        for fn in (self.clear_cpu, self.clear_ram, self.clear_gpu, self.clear_net):
            try:
                fn(server_id)
            except Exception:
                pass
