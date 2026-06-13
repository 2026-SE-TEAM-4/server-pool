"""모드·기준선 제어: docker exec로 모드 파일과 기준선 파일을 쓰거나 지운다.

build_* 는 순수 함수라 docker 없이 테스트한다. SimControl은 DockerControl로 디스패치한다.
"""

from app import config
from app.docker_control import DockerControl

VALID_MODES = ("stable", "real", "randomwalk")

_BASELINE_PATHS = {
    "cpu": config.CPU_BASELINE_PATH,
    "ram": config.MEM_BASELINE_PATH,
    "gpu": config.GPU_BASELINE_PATH,
    "net": config.NET_BASELINE_PATH,
}


def build_set_mode_cmd(mode: str) -> list[str]:
    if mode not in VALID_MODES:
        raise ValueError(f"unknown mode: {mode}")
    return ["sh", "-c", f"echo {mode} > {config.MODE_PATH}"]


def build_set_baseline_cmd(path: str, pct: int) -> list[str]:
    value = max(0, min(100, pct))
    return ["sh", "-c", f"echo {value} > {path}"]


def build_clear_cmd(path: str) -> list[str]:
    return ["rm", "-f", path]


class SimControl:
    """DockerControl을 통해 모드·기준선 파일을 쓰거나 지운다."""

    def __init__(self, docker: DockerControl) -> None:
        self._docker = docker

    def set_mode(self, server_id: int, mode: str) -> None:
        self._docker.exec_run(server_id, build_set_mode_cmd(mode))

    def reset_mode(self, server_id: int) -> None:
        self._docker.exec_run(server_id, build_clear_cmd(config.MODE_PATH))

    def set_baseline(self, server_id: int, resource: str, pct: int) -> None:
        self._docker.exec_run(server_id, build_set_baseline_cmd(_BASELINE_PATHS[resource], pct))

    def clear_baseline(self, server_id: int, resource: str) -> None:
        self._docker.exec_run(server_id, build_clear_cmd(_BASELINE_PATHS[resource]))
