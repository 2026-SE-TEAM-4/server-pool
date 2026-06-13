# server-pool 테스트 툴 (PyQt GUI) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** server-pool 에이전트 6대에 GUI로 부하/장애/카오스 상황을 주입하는 PyQt 데스크톱 테스트 툴을 만든다.

**Architecture:** `server-pool/testtool/`에 에이전트와 분리된 PyQt6 앱을 둔다. CPU/RAM은 `docker exec`로 컨테이너 안 파이썬 부하 프로세스를 띄워 실부하를 주입하고(센티넬 `pkill`로 중지), GPU는 `docker exec`로 오버라이드 파일을 써서 합성값을 덮는다. 도커 수명주기는 docker-py로 제어한다. 블로킹 호출(docker/HTTP)은 QThreadPool 워커에서 돌려 UI를 막지 않는다.

**Tech Stack:** Python 3.12, PyQt6, docker(SDK), httpx, pytest.

---

## File Structure

생성:
- `testtool/pyproject.toml` — PyQt6+docker+httpx 의존성, pytest 설정
- `testtool/README.md`
- `testtool/app/__init__.py`
- `testtool/app/config.py` — 매핑·상수·센티넬
- `testtool/app/docker_control.py` — docker-py 래퍼
- `testtool/app/agent_client.py` — httpx 메트릭 클라이언트
- `testtool/app/load_injector.py` — 부하 명령 생성·주입·중지, GPU 오버라이드
- `testtool/app/poller.py` — QThreadPool 백그라운드 폴러
- `testtool/app/scenarios.py` — 카오스 엔진(순수) + 러너(QObject)
- `testtool/app/ui/__init__.py`
- `testtool/app/ui/server_table.py`
- `testtool/app/ui/server_panel.py`
- `testtool/app/ui/scenario_panel.py`
- `testtool/app/ui/log_panel.py`
- `testtool/app/ui/main_window.py`
- `testtool/app/main.py` — 진입점
- `testtool/tests/__init__.py`
- `testtool/tests/test_config.py`
- `testtool/tests/test_docker_control.py`
- `testtool/tests/test_agent_client.py`
- `testtool/tests/test_load_injector.py`
- `testtool/tests/test_scenarios.py`

수정:
- `agent/collectors/gpu.py` — GPU 오버라이드 파일 처리
- `tests/test_collectors.py` — GPU 오버라이드 테스트 추가
- `tree.md` — `testtool/` 반영, gpu 주석 갱신

---

## Task 1: 에이전트 GPU 오버라이드

테스트 툴이 컨테이너 안에 쓴 오버라이드 파일이 있으면 GPU 합성값 대신 그 값을 반환한다. 파일이 없으면 기존 동작 그대로(완전 inert).

**Files:**
- Modify: `agent/collectors/gpu.py`
- Test: `tests/test_collectors.py`

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_collectors.py` 끝에 추가

```python
import agent.collectors.gpu as gpu_mod


def test_gpu_override_returns_file_value(tmp_path, monkeypatch) -> None:
    override = tmp_path / "gpu_override"
    override.write_text("73.5")
    monkeypatch.setattr(gpu_mod, "GPU_OVERRIDE_PATH", str(override))
    monkeypatch.setattr(gpu_mod, "GPU_SIMULATE", True)
    assert gpu_mod.read_gpu_usage() == 73.5


def test_gpu_override_ignored_when_out_of_range(tmp_path, monkeypatch) -> None:
    override = tmp_path / "gpu_override"
    override.write_text("250")
    monkeypatch.setattr(gpu_mod, "GPU_OVERRIDE_PATH", str(override))
    monkeypatch.setattr(gpu_mod, "GPU_SIMULATE", True)
    value = gpu_mod.read_gpu_usage()
    assert 0.0 <= value <= 100.0  # 범위 밖 오버라이드는 무시, 합성값 사용


def test_gpu_override_ignored_when_not_simulated(tmp_path, monkeypatch) -> None:
    override = tmp_path / "gpu_override"
    override.write_text("50")
    monkeypatch.setattr(gpu_mod, "GPU_OVERRIDE_PATH", str(override))
    monkeypatch.setattr(gpu_mod, "GPU_SIMULATE", False)
    assert gpu_mod.read_gpu_usage() is None  # GPU 미탑재 서버는 항상 None
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_collectors.py -v`
Expected: FAIL — `module 'agent.collectors.gpu' has no attribute 'GPU_OVERRIDE_PATH'`

- [ ] **Step 3: gpu.py 구현** — 파일 전체를 아래로 교체

```python
"""GPU 사용률 수집기.

시뮬레이션 환경(에이전트 컨테이너)에는 물리 GPU가 없다. GPU_SIMULATE가
켜져 있으면 서버별로 다른 합성 사용률을 만들어 대시보드 시연이 의미 있게 하고,
꺼져 있으면 None(GPU 미탑재)을 반환한다. 실제 GPU 노드 연동은 후속 과제다.

GPU_SIMULATE는 config.py에서 서버 스펙의 gpu_model 유무에 따라 자동 결정된다.
GPU가 없는 서버(cpu-xeon-01, cpu-epyc-01)는 항상 None을 반환한다.

테스트 툴은 합성값을 외부에서 덮을 수 있어야 한다(에이전트 프로세스 내부 값이라
docker exec로 직접 못 바꾼다). GPU_OVERRIDE_PATH 파일이 있으면 그 값을 읽어
반환한다. 파일이 없으면(평상시) 완전히 inert하므로 운영에 영향이 없다. 왜 파일인가:
FastAPI 제어 라우터를 추가하지 않고 가장 가벼운 IPC로 끝내기 위해서다.
"""

import random

from agent.config import GPU_SIMULATE, SERVER_ID

# 테스트 툴이 docker exec로 기록하는 오버라이드 파일 경로.
GPU_OVERRIDE_PATH = "/tmp/agent_gpu_override"

# 서버마다 다른 곡선을 그리도록 SERVER_ID로 시드한 난수원. 직전 값 주변에서
# 완만히 움직이는 합성 사용률을 유지한다(0~100 범위).
_rng = random.Random(SERVER_ID)
_value = _rng.uniform(20.0, 80.0)


def _read_override() -> float | None:
    """오버라이드 파일 값을 읽는다. 없거나 0~100 밖이면 None."""
    try:
        with open(GPU_OVERRIDE_PATH) as f:
            value = float(f.read().strip())
    except (OSError, ValueError):
        return None
    if 0.0 <= value <= 100.0:
        return round(value, 1)
    return None


def read_gpu_usage() -> float | None:
    """GPU 사용률(%)을 반환한다. GPU_SIMULATE가 꺼져 있으면 None."""
    global _value
    if not GPU_SIMULATE:
        return None
    override = _read_override()
    if override is not None:
        return override
    _value = max(0.0, min(100.0, _value + _rng.uniform(-5.0, 5.0)))
    return round(_value, 1)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_collectors.py -v`
Expected: PASS (기존 4개 + 신규 3개)

- [ ] **Step 5: 커밋**

```bash
git add agent/collectors/gpu.py tests/test_collectors.py
git commit -m "feat: GPU 합성값 오버라이드 파일 지원 (테스트 툴용)"
```

---

## Task 2: testtool 패키지 스캐폴드 + config

**Files:**
- Create: `testtool/pyproject.toml`, `testtool/app/__init__.py`, `testtool/app/ui/__init__.py`, `testtool/tests/__init__.py`, `testtool/app/config.py`, `testtool/README.md`
- Test: `testtool/tests/test_config.py`

- [ ] **Step 1: pyproject.toml 작성** — `testtool/pyproject.toml`

```toml
[project]
name = "server-pool-testtool"
version = "0.1.0"
description = "서버 풀 GUI 테스트 콘솔 (부하/장애/카오스 주입)"
requires-python = ">=3.12,<3.13"
dependencies = [
    "PyQt6>=6.7",
    "docker>=7",
    "httpx>=0.27",
]

[tool.uv]
package = false

[dependency-groups]
dev = ["pytest>=8", "pytest-qt>=4"]

[tool.pytest.ini_options]
pythonpath = ["."]
```

- [ ] **Step 2: 빈 패키지 파일 생성**

`testtool/app/__init__.py`, `testtool/app/ui/__init__.py`, `testtool/tests/__init__.py` — 각각 빈 파일.

- [ ] **Step 3: config 실패 테스트 작성** — `testtool/tests/test_config.py`

```python
from app import config


def test_agent_port_is_base_plus_id():
    assert config.agent_port(1) == 9101
    assert config.agent_port(6) == 9106


def test_service_name():
    assert config.service_name(3) == "agent-3"


def test_service_to_server_id():
    assert config.service_to_server_id("agent-3") == 3
    assert config.service_to_server_id("agent-12") == 12
    assert config.service_to_server_id("postgres") is None
    assert config.service_to_server_id("agent-x") is None


def test_server_ids_default():
    assert config.SERVER_IDS == [1, 2, 3, 4, 5, 6]
```

- [ ] **Step 4: 실패 확인**

Run: `cd testtool && uv run pytest tests/test_config.py -v`
Expected: FAIL — `No module named 'app.config'`

- [ ] **Step 5: config.py 구현** — `testtool/app/config.py`

```python
"""테스트 툴 상수와 매핑.

server-pool/docker-compose.yml 규약: 서비스명 agent-N, 퍼블리시 포트 9100+N.
에이전트는 호스트에서 127.0.0.1:<port>로 도달한다.
"""

# 도커 compose 서비스명 → SERVER_ID 발견에 쓰는 라벨 키.
COMPOSE_SERVICE_LABEL = "com.docker.compose.service"

SERVER_IDS = [1, 2, 3, 4, 5, 6]
AGENT_HOST = "127.0.0.1"
BASE_PORT = 9100  # 포트 = BASE_PORT + SERVER_ID

# 에이전트가 읽는 GPU 오버라이드 파일(agent/collectors/gpu.py와 동일 경로).
GPU_OVERRIDE_PATH = "/tmp/agent_gpu_override"

# 부하 프로세스 식별 센티넬(중지 시 pkill -f 매칭). CPU/RAM 분리.
CPU_LOAD_SENTINEL = "testtool_cpu_load"
RAM_LOAD_SENTINEL = "testtool_ram_load"

# RAM 부하 안전 예산: 100%일 때 컨테이너 안에서 할당할 MB.
# 스펙 RAM(수백 GB)을 그대로 쓰면 호스트가 OOM되므로 안전한 상한을 둔다.
# 실부하라 보고되는 호스트 RAM%는 정확히 목표치가 되지 않는다(의도된 현실성).
RAM_LOAD_MB_PER_100 = 2048

# 폴링 주기(ms).
POLL_INTERVAL_MS = 2500


def agent_port(server_id: int) -> int:
    return BASE_PORT + server_id


def service_name(server_id: int) -> str:
    return f"agent-{server_id}"


def service_to_server_id(service: str) -> int | None:
    """compose 서비스명 'agent-N' → N. 매칭 안 되면 None."""
    if not service.startswith("agent-"):
        return None
    suffix = service.split("-", 1)[1]
    if not suffix.isdigit():
        return None
    return int(suffix)
```

- [ ] **Step 6: 통과 확인**

Run: `cd testtool && uv run pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 7: README 작성** — `testtool/README.md`

```markdown
# server-pool 테스트 콘솔

서버 풀 에이전트 컨테이너에 부하/장애/카오스 상황을 GUI로 주입하는 PyQt 데스크톱 툴.

## 사전 준비

먼저 서버 풀을 띄운다:

    cd server-pool
    docker compose up --build -d

## 실행

    cd server-pool/testtool
    uv sync
    uv run python -m app.main

## 기능

- 서버(컨테이너) 목록·상태·실시간 메트릭(CPU/RAM/GPU/Net)
- 서버별 CPU/RAM/GPU 되돌리기 / 50% / 100%
- 서버 강제 정지 / 재시작
- 카오스 시나리오: 전체 과부하 / 랜덤 정지 / 랜덤 부하 스파이크 (랜덤 + n분)

## 동작 방식

- CPU/RAM: docker exec로 컨테이너 안 파이썬 부하 프로세스 기동(실부하). 중지는 센티넬 pkill.
- GPU: docker exec로 오버라이드 파일(`/tmp/agent_gpu_override`) 기록. 에이전트 gpu 수집기가 읽는다.
- 도커 수명주기: docker SDK.

> 실부하라 CPU/RAM은 정확히 50%/100%가 되지 않는다(의도된 현실성). RAM은 호스트 OOM 방지를 위해 안전 예산(config.RAM_LOAD_MB_PER_100) 내에서만 할당한다.
```

- [ ] **Step 8: 커밋**

```bash
git add testtool/pyproject.toml testtool/app/__init__.py testtool/app/ui/__init__.py testtool/tests/__init__.py testtool/app/config.py testtool/tests/test_config.py testtool/README.md
git commit -m "feat: testtool 스캐폴드 + config 매핑"
```

---

## Task 3: load_injector (부하 명령 생성·주입)

순수 명령 빌더와 docker 주입을 분리한다. 빌더는 docker 없이 테스트한다.

**Files:**
- Create: `testtool/app/load_injector.py`
- Test: `testtool/tests/test_load_injector.py`

- [ ] **Step 1: 실패 테스트 작성** — `testtool/tests/test_load_injector.py`

```python
from app import config
from app import load_injector as li


def test_cpu_cmd_contains_sentinel_and_load():
    cmd = li.build_cpu_cmd(50)
    joined = " ".join(cmd)
    assert config.CPU_LOAD_SENTINEL in joined
    assert "0.5" in joined  # 50% → load fraction 0.5
    assert cmd[0] == "python"


def test_ram_cmd_scales_mb_by_percent():
    cmd = li.build_ram_cmd(50)
    joined = " ".join(cmd)
    assert config.RAM_LOAD_SENTINEL in joined
    # 50% → RAM_LOAD_MB_PER_100의 절반 MB
    assert str(config.RAM_LOAD_MB_PER_100 // 2) in joined


def test_pkill_cmd_targets_sentinel():
    assert li.build_pkill_cmd(config.CPU_LOAD_SENTINEL) == [
        "pkill", "-f", config.CPU_LOAD_SENTINEL,
    ]


def test_gpu_set_cmd_writes_override_file():
    cmd = li.build_gpu_set_cmd(80)
    assert cmd[0] == "sh"
    joined = " ".join(cmd)
    assert config.GPU_OVERRIDE_PATH in joined
    assert "80" in joined


def test_gpu_clear_cmd_removes_file():
    assert li.build_gpu_clear_cmd() == ["rm", "-f", config.GPU_OVERRIDE_PATH]
```

- [ ] **Step 2: 실패 확인**

Run: `cd testtool && uv run pytest tests/test_load_injector.py -v`
Expected: FAIL — `No module named 'app.load_injector'`

- [ ] **Step 3: load_injector.py 구현** — `testtool/app/load_injector.py`

```python
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
```

> 참고: `DockerControl`은 Task 4에서 정의한다. 이 모듈은 import만 하고 인터페이스(`exec_detached`, `exec_run`)에 의존한다. Task 4가 먼저 머지돼야 import가 동작하므로, 실행 순서는 Task 4 → Task 3 빌더 테스트로 잡거나, 이 단계에선 빌더 테스트만 통과시키고(아래 Step 4) 클래스 통합은 Task 4 후 확인한다.

- [ ] **Step 4: 빌더 테스트 통과 확인**

Run: `cd testtool && uv run pytest tests/test_load_injector.py -v`
Expected: PASS (빌더 함수 5개 테스트). `from app.docker_control import DockerControl`가 Task 4 미완이면 import 에러가 난다 — 이 경우 Task 4를 먼저 수행하고 돌아온다.

- [ ] **Step 5: 커밋**

```bash
git add testtool/app/load_injector.py testtool/tests/test_load_injector.py
git commit -m "feat: load_injector 부하 명령 빌더·주입기"
```

---

## Task 4: docker_control (docker-py 래퍼)

**Files:**
- Create: `testtool/app/docker_control.py`
- Test: `testtool/tests/test_docker_control.py`

- [ ] **Step 1: 실패 테스트 작성** — `testtool/tests/test_docker_control.py`

```python
from unittest.mock import MagicMock

from app import config
from app.docker_control import DockerControl


def _fake_container(service: str, status: str = "running"):
    c = MagicMock()
    c.labels = {config.COMPOSE_SERVICE_LABEL: service}
    c.status = status
    return c


def _control_with(containers):
    client = MagicMock()
    client.containers.list.return_value = containers
    return DockerControl(client=client), client


def test_discover_maps_service_to_server_id():
    ctrl, _ = _control_with([_fake_container("agent-1"), _fake_container("agent-3")])
    found = ctrl.discover()
    assert set(found.keys()) == {1, 3}


def test_status_returns_offline_when_missing():
    ctrl, _ = _control_with([_fake_container("agent-1")])
    ctrl.discover()
    assert ctrl.status(1) == "running"
    assert ctrl.status(2) == "offline"


def test_stop_calls_container_stop():
    container = _fake_container("agent-1")
    ctrl, _ = _control_with([container])
    ctrl.discover()
    ctrl.stop(1)
    container.stop.assert_called_once()


def test_restart_calls_container_restart():
    container = _fake_container("agent-1")
    ctrl, _ = _control_with([container])
    ctrl.discover()
    ctrl.restart(1)
    container.restart.assert_called_once()


def test_exec_run_invokes_exec(monkeypatch):
    container = _fake_container("agent-1")
    ctrl, _ = _control_with([container])
    ctrl.discover()
    ctrl.exec_run(1, ["pkill", "-f", "x"])
    container.exec_run.assert_called_once_with(["pkill", "-f", "x"])


def test_exec_detached_invokes_exec_with_detach():
    container = _fake_container("agent-1")
    ctrl, _ = _control_with([container])
    ctrl.discover()
    ctrl.exec_detached(1, ["python", "-c", "x"])
    _, kwargs = container.exec_run.call_args
    assert kwargs.get("detach") is True
```

- [ ] **Step 2: 실패 확인**

Run: `cd testtool && uv run pytest tests/test_docker_control.py -v`
Expected: FAIL — `No module named 'app.docker_control'`

- [ ] **Step 3: docker_control.py 구현** — `testtool/app/docker_control.py`

```python
"""docker-py 래퍼: 컨테이너 발견·상태·수명주기·exec.

UI/Qt를 모른다. SERVER_ID로만 다룬다. compose 서비스 라벨(agent-N)로 컨테이너를
발견해 매핑한다. 모든 호출은 블로킹이므로 호출 측(poller)이 워커 스레드에서 부른다.
"""

import docker

from app import config


class DockerControl:
    def __init__(self, client=None) -> None:
        # client 주입은 테스트용. 실제 실행은 from_env로 도커 소켓에 붙는다.
        self._client = client or docker.from_env()
        self._by_id: dict[int, object] = {}

    def discover(self) -> dict[int, object]:
        """실행/정지 포함 모든 컨테이너에서 agent-N을 찾아 SERVER_ID로 매핑한다."""
        found: dict[int, object] = {}
        for container in self._client.containers.list(all=True):
            service = container.labels.get(config.COMPOSE_SERVICE_LABEL, "")
            server_id = config.service_to_server_id(service)
            if server_id is not None:
                found[server_id] = container
        self._by_id = found
        return found

    def _get(self, server_id: int):
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
```

> `status()`가 `container.reload()`를 부르는데, 테스트의 MagicMock은 reload를 자동 무시(빈 메서드)하므로 status 값은 초기 설정값을 유지한다. 테스트는 그대로 통과한다.

- [ ] **Step 4: 통과 확인**

Run: `cd testtool && uv run pytest tests/test_docker_control.py tests/test_load_injector.py -v`
Expected: PASS (docker_control 6개 + load_injector 5개)

- [ ] **Step 5: 커밋**

```bash
git add testtool/app/docker_control.py testtool/tests/test_docker_control.py
git commit -m "feat: docker_control docker-py 래퍼"
```

---

## Task 5: agent_client (httpx 메트릭)

**Files:**
- Create: `testtool/app/agent_client.py`
- Test: `testtool/tests/test_agent_client.py`

- [ ] **Step 1: 실패 테스트 작성** — `testtool/tests/test_agent_client.py`

```python
import httpx

from app import agent_client as ac


def _client_returning(payload, status=200):
    def handler(request):
        return httpx.Response(status, json=payload)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_metrics_parses_payload():
    payload = {"cpuUsage": 42.0, "memUsage": 61.2, "gpuUsage": 88.0, "netUsage": 12.4}
    metrics = ac.fetch_metrics("h", 9101, client=_client_returning(payload))
    assert metrics.online is True
    assert metrics.cpu == 42.0
    assert metrics.gpu == 88.0


def test_fetch_metrics_offline_on_error():
    def handler(request):
        raise httpx.ConnectError("down")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    metrics = ac.fetch_metrics("h", 9101, client=client)
    assert metrics.online is False
    assert metrics.cpu is None


def test_fetch_metrics_offline_on_5xx():
    metrics = ac.fetch_metrics("h", 9101, client=_client_returning({}, status=503))
    assert metrics.online is False
```

- [ ] **Step 2: 실패 확인**

Run: `cd testtool && uv run pytest tests/test_agent_client.py -v`
Expected: FAIL — `No module named 'app.agent_client'`

- [ ] **Step 3: agent_client.py 구현** — `testtool/app/agent_client.py`

```python
"""에이전트 HTTP 클라이언트. /metrics를 읽고 미응답이면 명시적으로 offline 표현.

예외를 삼키지 않고 AgentMetrics(online=False)로 변환해 호출 측이 OFFLINE을
표시하게 한다. client 인자는 테스트 주입용(MockTransport).
"""

from dataclasses import dataclass

import httpx

from app import config


@dataclass
class AgentMetrics:
    online: bool
    cpu: float | None = None
    mem: float | None = None
    gpu: float | None = None
    net: float | None = None


def fetch_metrics(
    host: str, port: int, *, client: httpx.Client | None = None, timeout: float = 2.0
) -> AgentMetrics:
    own = client is None
    client = client or httpx.Client(timeout=timeout)
    try:
        resp = client.get(f"http://{host}:{port}/metrics")
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        return AgentMetrics(online=False)
    finally:
        if own:
            client.close()
    return AgentMetrics(
        online=True,
        cpu=data.get("cpuUsage"),
        mem=data.get("memUsage"),
        gpu=data.get("gpuUsage"),
        net=data.get("netUsage"),
    )


def fetch_for(server_id: int, **kwargs) -> AgentMetrics:
    return fetch_metrics(config.AGENT_HOST, config.agent_port(server_id), **kwargs)
```

- [ ] **Step 4: 통과 확인**

Run: `cd testtool && uv run pytest tests/test_agent_client.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add testtool/app/agent_client.py testtool/tests/test_agent_client.py
git commit -m "feat: agent_client httpx 메트릭 클라이언트"
```

---

## Task 6: scenarios (카오스 엔진 — 순수 결정 로직)

Qt와 분리한 순수 결정 엔진을 만든다. 시드 고정 RNG로 결정론 검증.

**Files:**
- Create: `testtool/app/scenarios.py`
- Test: `testtool/tests/test_scenarios.py`

- [ ] **Step 1: 실패 테스트 작성** — `testtool/tests/test_scenarios.py`

```python
import random

from app import scenarios as sc


def test_overload_all_loads_every_running_server_then_reverts():
    engine = sc.OverloadAll(server_ids=[1, 2], intensity=80, duration_s=60)
    start = engine.tick(elapsed_s=0, running={1, 2}, rng=random.Random(0))
    kinds = {(a.kind, a.server_id) for a in start}
    assert ("load_cpu", 1) in kinds
    assert ("load_ram", 2) in kinds
    # 만료 시 전체 revert
    end = engine.tick(elapsed_s=60, running={1, 2}, rng=random.Random(0))
    assert all(a.kind == "revert" for a in end)
    assert {a.server_id for a in end} == {1, 2}


def test_overload_all_is_done_after_duration():
    engine = sc.OverloadAll(server_ids=[1], intensity=80, duration_s=30)
    engine.tick(elapsed_s=0, running={1}, rng=random.Random(0))
    assert engine.is_done(elapsed_s=29) is False
    assert engine.is_done(elapsed_s=30) is True


def test_random_stop_stops_a_running_server():
    engine = sc.RandomStop(
        server_ids=[1, 2, 3], duration_s=300, stop_min_s=10, stop_max_s=60, every_s=5
    )
    actions = engine.tick(elapsed_s=5, running={1, 2, 3}, rng=random.Random(1))
    stops = [a for a in actions if a.kind == "stop"]
    assert len(stops) == 1
    assert stops[0].server_id in {1, 2, 3}
    assert 10 <= stops[0].value <= 60  # 정지 시간(초)


def test_random_stop_schedules_restart_after_value():
    engine = sc.RandomStop(
        server_ids=[1], duration_s=300, stop_min_s=10, stop_max_s=10, every_s=5
    )
    engine.tick(elapsed_s=5, running={1}, rng=random.Random(1))
    # 10초 뒤 재시작 예약. 정지 직후엔 start 없음, 15초엔 start.
    assert [a.kind for a in engine.tick(elapsed_s=6, running=set(), rng=random.Random(1))] == []
    restart = engine.tick(elapsed_s=15, running=set(), rng=random.Random(1))
    assert any(a.kind == "start" and a.server_id == 1 for a in restart)


def test_random_stop_deterministic_with_seed():
    def run():
        engine = sc.RandomStop(
            server_ids=[1, 2, 3], duration_s=300, stop_min_s=10, stop_max_s=60, every_s=5
        )
        return [a.server_id for a in engine.tick(5, {1, 2, 3}, random.Random(42)) if a.kind == "stop"]
    assert run() == run()
```

- [ ] **Step 2: 실패 확인**

Run: `cd testtool && uv run pytest tests/test_scenarios.py -v`
Expected: FAIL — `No module named 'app.scenarios'`

- [ ] **Step 3: scenarios.py 구현(순수 엔진 부분)** — `testtool/app/scenarios.py`

```python
"""카오스 시나리오: 순수 결정 엔진 + Qt 러너.

엔진(OverloadAll/RandomStop/RandomSpike)은 Qt를 모른다. tick(elapsed, running, rng)이
이번 틱에 수행할 Action 목록을 돌려준다. RNG는 외부 주입이라 시드 고정 시 결정론적이다.
러너(ChaosRunner)는 QTimer로 매초 tick을 호출하고 Action을 docker/injector로 디스패치한다.
중지 시 모든 부하/정지를 즉시 원복한다.
"""

from dataclasses import dataclass


@dataclass
class Action:
    kind: str  # load_cpu | load_ram | gpu | revert | stop | start
    server_id: int
    value: float | None = None  # 부하 %, GPU %, 또는 정지 시간(초)


class OverloadAll:
    """실행 중 모든 서버에 CPU/RAM 고부하를 duration_s 동안. 만료 시 전체 revert."""

    def __init__(self, server_ids, intensity, duration_s):
        self._ids = list(server_ids)
        self._intensity = intensity
        self._duration = duration_s
        self._applied = False
        self._reverted = False

    def tick(self, elapsed_s, running, rng):
        if elapsed_s >= self._duration:
            if self._reverted:
                return []
            self._reverted = True
            return [Action("revert", sid) for sid in self._ids]
        if self._applied:
            return []
        self._applied = True
        actions = []
        for sid in self._ids:
            if sid in running:
                actions.append(Action("load_cpu", sid, self._intensity))
                actions.append(Action("load_ram", sid, self._intensity))
        return actions

    def is_done(self, elapsed_s):
        return elapsed_s >= self._duration


class RandomStop:
    """every_s 마다 랜덤 실행 서버 하나를 stop_min~stop_max초 정지 후 재시작. duration_s까지."""

    def __init__(self, server_ids, duration_s, stop_min_s, stop_max_s, every_s):
        self._ids = list(server_ids)
        self._duration = duration_s
        self._stop_min = stop_min_s
        self._stop_max = stop_max_s
        self._every = every_s
        self._restart_at: dict[int, float] = {}  # server_id → 재시작 예정 elapsed

    def tick(self, elapsed_s, running, rng):
        actions = []
        # 재시작 예정 처리
        for sid, due in list(self._restart_at.items()):
            if elapsed_s >= due:
                actions.append(Action("start", sid))
                del self._restart_at[sid]
        # 정지 시도(주기마다, duration 내에서만)
        if elapsed_s > 0 and elapsed_s % self._every == 0 and elapsed_s < self._duration:
            candidates = [s for s in self._ids if s in running and s not in self._restart_at]
            if candidates:
                target = rng.choice(candidates)
                hold = rng.randint(self._stop_min, self._stop_max)
                self._restart_at[target] = elapsed_s + hold
                actions.append(Action("stop", target, hold))
        return actions

    def is_done(self, elapsed_s):
        # duration 경과 + 예약된 재시작이 모두 끝나야 종료
        return elapsed_s >= self._duration and not self._restart_at


class RandomSpike:
    """every_s 마다 랜덤 서버에 랜덤 강도 부하를 랜덤 시간 주입 후 자동 revert. duration_s까지."""

    def __init__(self, server_ids, duration_s, every_s, spike_min_s=10, spike_max_s=40):
        self._ids = list(server_ids)
        self._duration = duration_s
        self._every = every_s
        self._spike_min = spike_min_s
        self._spike_max = spike_max_s
        self._revert_at: dict[int, float] = {}

    def tick(self, elapsed_s, running, rng):
        actions = []
        for sid, due in list(self._revert_at.items()):
            if elapsed_s >= due:
                actions.append(Action("revert", sid))
                del self._revert_at[sid]
        if elapsed_s > 0 and elapsed_s % self._every == 0 and elapsed_s < self._duration:
            candidates = [s for s in self._ids if s in running and s not in self._revert_at]
            if candidates:
                target = rng.choice(candidates)
                intensity = rng.choice([50, 80, 100])
                hold = rng.randint(self._spike_min, self._spike_max)
                self._revert_at[target] = elapsed_s + hold
                actions.append(Action("load_cpu", target, intensity))
        return actions

    def is_done(self, elapsed_s):
        return elapsed_s >= self._duration and not self._revert_at
```

- [ ] **Step 4: 통과 확인**

Run: `cd testtool && uv run pytest tests/test_scenarios.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add testtool/app/scenarios.py testtool/tests/test_scenarios.py
git commit -m "feat: 카오스 시나리오 순수 결정 엔진"
```

---

## Task 7: ChaosRunner (Qt 러너) + poller

UI를 막지 않는 백그라운드 폴러와, 엔진을 매초 구동하는 러너를 만든다. Qt 의존이라 단위테스트 대신 스모크로 둔다.

**Files:**
- Create: `testtool/app/poller.py`
- Modify: `testtool/app/scenarios.py` (ChaosRunner 추가)

- [ ] **Step 1: poller.py 구현** — `testtool/app/poller.py`

```python
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
```

- [ ] **Step 2: ChaosRunner 추가** — `testtool/app/scenarios.py` 끝에 append

```python
from PyQt6.QtCore import QObject, QTimer, pyqtSignal  # noqa: E402


class ChaosRunner(QObject):
    """엔진을 매초 구동하고 Action을 docker/injector로 디스패치한다.

    running 집합은 폴러 스냅샷으로 갱신된다(set_running). 중지 시 그동안 부하/정지한
    모든 서버를 즉시 원복한다.
    """

    log = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, engine, docker, injector, rng, parent=None):
        super().__init__(parent)
        self._engine = engine
        self._docker = docker
        self._injector = injector
        self._rng = rng
        self._elapsed = 0
        self._running: set[int] = set()
        self._touched: set[int] = set()  # 부하/정지를 가한 서버(원복 대상)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)

    def set_running(self, running):
        self._running = set(running)

    def start(self):
        self._elapsed = 0
        self._timer.start()

    def _tick(self):
        actions = self._engine.tick(self._elapsed, self._running, self._rng)
        for a in actions:
            self._dispatch(a)
        self._elapsed += 1
        if self._engine.is_done(self._elapsed):
            self.stop()

    def _dispatch(self, a):
        self._touched.add(a.server_id)
        if a.kind == "load_cpu":
            self._injector.apply_cpu(a.server_id, int(a.value))
            self.log.emit(f"agent-{a.server_id} CPU {int(a.value)}% 부하 주입")
        elif a.kind == "load_ram":
            self._injector.apply_ram(a.server_id, int(a.value))
            self.log.emit(f"agent-{a.server_id} RAM {int(a.value)}% 부하 주입")
        elif a.kind == "gpu":
            self._injector.set_gpu(a.server_id, int(a.value))
            self.log.emit(f"agent-{a.server_id} GPU {int(a.value)}% 설정")
        elif a.kind == "revert":
            self._injector.revert_all(a.server_id)
            self.log.emit(f"agent-{a.server_id} 부하 원복")
        elif a.kind == "stop":
            self._docker.stop(a.server_id)
            self.log.emit(f"agent-{a.server_id} 정지 ({int(a.value)}초)")
        elif a.kind == "start":
            self._docker.start(a.server_id)
            self.log.emit(f"agent-{a.server_id} 재시작")

    def stop(self):
        self._timer.stop()
        for sid in self._touched:
            self._injector.revert_all(sid)
            self._docker.start(sid)  # 정지돼 있었다면 복구(이미 떠 있으면 무해)
        self.log.emit("카오스 중지 — 전체 원복")
        self._touched.clear()
        self.finished.emit()
```

- [ ] **Step 3: import 스모크 확인**

Run: `cd testtool && uv run python -c "from app import poller, scenarios; print('ok')"`
Expected: 출력 `ok` (PyQt6 import 성공)

- [ ] **Step 4: 커밋**

```bash
git add testtool/app/poller.py testtool/app/scenarios.py
git commit -m "feat: 백그라운드 폴러 + 카오스 Qt 러너"
```

---

## Task 8: UI 위젯 (테이블·서버패널·시나리오패널·로그)

Qt 위젯. 상태를 직접 만들지 않고 시그널로 받는다.

**Files:**
- Create: `testtool/app/ui/server_table.py`, `server_panel.py`, `scenario_panel.py`, `log_panel.py`

- [ ] **Step 1: log_panel.py** — `testtool/app/ui/log_panel.py`

```python
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
```

- [ ] **Step 2: server_table.py** — `testtool/app/ui/server_table.py`

```python
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
```

- [ ] **Step 3: server_panel.py** — `testtool/app/ui/server_panel.py`

```python
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
```

- [ ] **Step 4: scenario_panel.py** — `testtool/app/ui/scenario_panel.py`

```python
"""카오스 시나리오 선택·파라미터·시작/중지."""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QPushButton, QSpinBox, QVBoxLayout,
)

SCENARIOS = ["전체 과부하", "랜덤 정지", "랜덤 부하 스파이크"]


class ScenarioPanel(QGroupBox):
    startRequested = pyqtSignal(dict)  # {scenario, duration_min, stop_min, stop_max, intensity}
    stopRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("카오스 시나리오", parent)
        self._combo = QComboBox()
        self._combo.addItems(SCENARIOS)
        self._duration = self._spin(1, 120, 5)
        self._stop_min = self._spin(1, 600, 10)
        self._stop_max = self._spin(1, 600, 60)
        self._intensity = self._spin(10, 100, 80)
        form = QFormLayout()
        form.addRow("시나리오", self._combo)
        form.addRow("지속(분)", self._duration)
        form.addRow("정지 최소(초)", self._stop_min)
        form.addRow("정지 최대(초)", self._stop_max)
        form.addRow("강도(%)", self._intensity)
        buttons = QHBoxLayout()
        start_btn = QPushButton("▶ 시작")
        stop_btn = QPushButton("■ 중지")
        start_btn.clicked.connect(self._emit_start)
        stop_btn.clicked.connect(self.stopRequested)
        buttons.addWidget(start_btn)
        buttons.addWidget(stop_btn)
        outer = QVBoxLayout(self)
        outer.addLayout(form)
        outer.addLayout(buttons)

    @staticmethod
    def _spin(low, high, default):
        s = QSpinBox()
        s.setRange(low, high)
        s.setValue(default)
        return s

    def _emit_start(self):
        self.startRequested.emit(
            {
                "scenario": self._combo.currentText(),
                "duration_min": self._duration.value(),
                "stop_min": self._stop_min.value(),
                "stop_max": self._stop_max.value(),
                "intensity": self._intensity.value(),
            }
        )
```

- [ ] **Step 5: import 스모크 확인**

Run: `cd testtool && uv run python -c "from app.ui import server_table, server_panel, scenario_panel, log_panel; print('ok')"`
Expected: 출력 `ok`

- [ ] **Step 6: 커밋**

```bash
git add testtool/app/ui/log_panel.py testtool/app/ui/server_table.py testtool/app/ui/server_panel.py testtool/app/ui/scenario_panel.py
git commit -m "feat: UI 위젯(테이블·서버패널·시나리오패널·로그)"
```

---

## Task 9: main_window + main 진입점 (조립)

모든 조각을 연결한다. 액션 디스패치는 QThreadPool로 떼어내 UI를 막지 않는다.

**Files:**
- Create: `testtool/app/ui/main_window.py`, `testtool/app/main.py`

- [ ] **Step 1: main_window.py** — `testtool/app/ui/main_window.py`

```python
"""전체 조립: 폴러 → 테이블, 패널 시그널 → 액션 디스패치, 시나리오 → 러너."""

import random

from PyQt6.QtCore import QRunnable, QThreadPool
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
    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            self._fn()
        except Exception:
            pass


class MainWindow(QWidget):
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
        self._poller.start()

    def _run_async(self, fn):
        self._pool.start(_Task(fn))

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
```

- [ ] **Step 2: main.py** — `testtool/app/main.py`

```python
"""진입점. docker 소켓 연결 실패 시 안내 후 종료."""

import sys

from PyQt6.QtWidgets import QApplication, QMessageBox

from app.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    try:
        window = MainWindow()
    except Exception as exc:  # docker.from_env 실패 등
        QMessageBox.critical(None, "초기화 실패", f"도커 연결 실패: {exc}")
        return 1
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: import 스모크 확인**

Run: `cd testtool && uv run python -c "from app.ui.main_window import MainWindow; print('ok')"`
Expected: 출력 `ok`

- [ ] **Step 4: 커밋**

```bash
git add testtool/app/ui/main_window.py testtool/app/main.py
git commit -m "feat: main_window 조립 + 진입점"
```

---

## Task 10: 전체 테스트·tree.md 갱신·마무리

**Files:**
- Modify: `tree.md`

- [ ] **Step 1: 전체 단위테스트 통과 확인**

Run: `cd testtool && uv run pytest -v`
Expected: 모든 테스트 PASS (config 4 + load_injector 5 + docker_control 6 + agent_client 3 + scenarios 5)

- [ ] **Step 2: 에이전트 테스트도 통과 확인**

Run: `uv run pytest tests/ -v`
Expected: 모든 테스트 PASS (기존 + GPU 오버라이드 3)

- [ ] **Step 3: tree.md 갱신** — `tree.md`의 디렉토리 트리에 testtool 추가

```text
server-pool/
├── agent/                     # 에이전트 패키지 (모든 코드는 이 안)
│   ├── main.py
│   ├── config.py
│   └── collectors/            # cpu.py, memory.py, net.py, gpu.py
├── testtool/                  # PyQt GUI 테스트 콘솔 (에이전트와 분리)
│   ├── app/                   # config·docker_control·agent_client·load_injector
│   │                          # poller·scenarios·ui/
│   ├── tests/                 # 비-UI 로직 단위테스트
│   ├── pyproject.toml         # PyQt6·docker·httpx (에이전트 의존성과 분리)
│   └── README.md
├── tests/                     # 수집기 단위 테스트
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── README.md
├── CLAUDE.md
├── tree.md
└── rule.md
```

`tree.md` 설계 원칙 섹션 아래에 한 줄 추가:

```text
- `testtool/` 은 운영 에이전트가 아니라 개발/시연용 GUI 부하·장애 주입 콘솔이다.
  에이전트 이미지에 포함되지 않으며 호스트에서 직접 실행한다(docker 소켓·퍼블리시 포트 사용).
```

- [ ] **Step 4: 커밋**

```bash
git add tree.md
git commit -m "docs: tree.md에 testtool 반영"
```

- [ ] **Step 5: 수동 동작 확인(선택)**

서버 풀을 띄운 상태에서:

```bash
cd server-pool && docker compose up --build -d
cd testtool && uv sync && uv run python -m app.main
```

확인: 서버 6행 표시, 상태/메트릭 갱신, 한 서버 CPU 100% 클릭 후 몇 초 뒤 CPU% 상승, GPU 50% 클릭 시 즉시 반영, 정지/재시작 동작, 카오스 "전체 과부하" 시작/중지 시 로그·원복.

---

## Self-Review 메모

- 스펙 커버리지: 목록/상태(Task 8·7), CPU/RAM/GPU 되돌리기·50·100(Task 3·8·9), 정지/재시작(Task 4·8·9), 카오스 3종 랜덤+n분(Task 6·7·9), GPU 오버라이드(Task 1). Net 직접제어 제외는 스펙 YAGNI와 일치.
- 타입 일관성: `DockerControl.exec_run/exec_detached/start/stop/restart`, `LoadInjector.apply_cpu/clear_cpu/apply_ram/clear_ram/set_gpu/clear_gpu/revert_all`, `Action(kind,server_id,value)`, `AgentMetrics(online,cpu,mem,gpu,net)`, `ServerSnapshot(server_id,status,metrics)` — 태스크 전반에서 동일 시그니처 사용.
- 실행 순서 주의: Task 3의 `LoadInjector`가 `app.docker_control`을 import하므로 Task 4를 먼저(또는 함께) 머지해야 import가 풀린다. 빌더 함수 테스트는 독립.
