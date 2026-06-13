"""부하 주입: CPU/RAM 실부하 프로세스, GPU 오버라이드 파일.

명령 빌더(build_*)는 순수 함수라 docker 없이 테스트한다. apply_*/clear_*는
docker_control로 컨테이너 안에서 실행한다. 부하 프로세스는 명령줄에 센티넬을
포함시켜 중지 시 pkill -f로 정리한다(CPU/RAM 센티넬 분리 → 자원별 독립 중지).
"""

from app import config
from app.docker_control import DockerControl

# 컨테이너 안에서 도는 CPU 부하 코드. argv[1]=부하율(0~1), argv[2]=센티넬(매칭용).
# fork된 워커는 argv를 상속하므로 pkill -f 센티넬로 함께 정리된다.
_CPU_CODE = (
    "import multiprocessing as mp,time,sys\n"
    "load=float(sys.argv[1]);n=mp.cpu_count()\n"
    "def burn():\n"
    " while True:\n"
    "  t=time.time()\n"
    "  while time.time()-t<load*0.1: pass\n"
    "  s=(1-load)*0.1\n"
    "  if s>0: time.sleep(s)\n"
    "ps=[mp.Process(target=burn,daemon=True) for _ in range(n)]\n"
    "[p.start() for p in ps]\n"
    "time.sleep(10**9)\n"
)

# RAM 부하 코드. argv[1]=할당 MB, argv[2]=센티넬.
_RAM_CODE = (
    "import sys,time\n"
    "mb=int(sys.argv[1])\n"
    "buf=bytearray(mb*1024*1024)\n"
    "for i in range(0,len(buf),4096): buf[i]=1\n"
    "time.sleep(10**9)\n"
)


def build_cpu_cmd(pct: int) -> list[str]:
    """pct(%)만큼 CPU 부하를 거는 docker exec 명령."""
    load = max(0.0, min(1.0, pct / 100))
    return ["python", "-c", _CPU_CODE, str(load), config.CPU_LOAD_SENTINEL]


def build_ram_cmd(pct: int) -> list[str]:
    """pct(%)에 비례한 MB를 할당하는 docker exec 명령(안전 예산 내)."""
    mb = config.RAM_LOAD_MB_PER_100 * max(0, min(100, pct)) // 100
    return ["python", "-c", _RAM_CODE, str(mb), config.RAM_LOAD_SENTINEL]


def build_pkill_cmd(sentinel: str) -> list[str]:
    return ["pkill", "-f", sentinel]


def build_gpu_set_cmd(pct: int) -> list[str]:
    value = max(0, min(100, pct))
    return ["sh", "-c", f"echo {value} > {config.GPU_OVERRIDE_PATH}"]


def build_gpu_clear_cmd() -> list[str]:
    return ["rm", "-f", config.GPU_OVERRIDE_PATH]


class LoadInjector:
    """docker_control을 통해 부하를 주입/해제한다."""

    def __init__(self, docker: DockerControl) -> None:
        self._docker = docker

    def apply_cpu(self, server_id: int, pct: int) -> None:
        self._docker.exec_detached(server_id, build_cpu_cmd(pct))

    def clear_cpu(self, server_id: int) -> None:
        self._docker.exec_run(server_id, build_pkill_cmd(config.CPU_LOAD_SENTINEL))

    def apply_ram(self, server_id: int, pct: int) -> None:
        self._docker.exec_detached(server_id, build_ram_cmd(pct))

    def clear_ram(self, server_id: int) -> None:
        self._docker.exec_run(server_id, build_pkill_cmd(config.RAM_LOAD_SENTINEL))

    def set_gpu(self, server_id: int, pct: int) -> None:
        self._docker.exec_run(server_id, build_gpu_set_cmd(pct))

    def clear_gpu(self, server_id: int) -> None:
        self._docker.exec_run(server_id, build_gpu_clear_cmd())

    def revert_all(self, server_id: int) -> None:
        """한 서버의 모든 부하/오버라이드를 되돌린다. 개별 실패는 무시(이미 없을 수 있음)."""
        for fn in (self.clear_cpu, self.clear_ram, self.clear_gpu):
            try:
                fn(server_id)
            except Exception:
                pass
