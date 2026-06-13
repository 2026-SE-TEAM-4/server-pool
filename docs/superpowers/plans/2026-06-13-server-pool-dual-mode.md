# server-pool 듀얼 모드 + testtool 확장 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** server-pool 에이전트에 안정 합성(stable) 메인 모드와 서브(real/randomwalk) 모드를 추가하고, testtool에 모드 전환·서버별 기준선 지정·실무형 카오스 2종·다크 모던 테마를 더한다.

**Architecture:** 컨테이너 단위 `/tmp/agent_mode` 파일 토글로 모드를 정한다. 각 수집기는 `override 파일 > stable 드리프트 > real psutil > randomwalk` 우선순위로 값을 낸다. stable은 자원별 기준선 파일을 중심으로 0.5~2%씩 평균회귀한다. testtool은 docker exec로 모드·기준선 파일을 쓰고, PyQt GUI에 제어·테마를 더한다.

**Tech Stack:** Python 3.12, FastAPI, psutil, uv, pytest (agent) / PyQt6, docker SDK, httpx, pytest (testtool)

---

## 파일 구조

agent:
- Create `agent/sim.py` — 모드 판정, 공용 백분율 파일 리더, `MeanRevertSim`.
- Modify `agent/config.py` — `DEFAULT_MODE` 추가, `METRIC_SIMULATE` 제거.
- Modify `agent/collectors/cpu.py` `memory.py` `gpu.py` `net.py` — 우선순위 재작성.
- Modify `tests/test_collectors.py` — 모드·우선순위·드리프트 테스트.

testtool:
- Modify `app/config.py` — mode·baseline·net override 경로.
- Create `app/sim_control.py` — 모드·기준선 docker exec 제어.
- Modify `app/load_injector.py` — `apply_net`/`clear_net`, `revert_all`에 net 포함.
- Modify `app/scenarios.py` — `MemoryLeak`·`CascadingFailure` 엔진, `load_net` dispatch.
- Create `app/ui/theme.py` — 다크 모던 QSS + 임계 색상 상수.
- Create `app/ui/sim_panel.py` — 모드 토글·자원별 기준선 슬라이더.
- Modify `app/ui/server_table.py` — 임계 색상.
- Modify `app/ui/scenario_panel.py` — 신규 시나리오 2종.
- Modify `app/ui/main_window.py` — sim_panel 배선, 신규 엔진 빌드.
- Modify `app/main.py` — 테마 적용.
- Modify `tests/` — sim_control·신규 시나리오 단위 테스트.

docs:
- Modify `tree.md`, `README.md`, `testtool/README.md`, 루트 `CLAUDE.md`.

작업 디렉토리: 모든 명령은 `server-pool/`(agent) 또는 `server-pool/testtool/`에서 실행한다.
브랜치는 이미 `feat/dual-mode-sim`.

---

## Task 1: agent/sim.py — 모드·공용 리더·평균회귀

**Files:**
- Create: `agent/sim.py`
- Test: `tests/test_sim.py`

- [ ] **Step 1: 실패하는 테스트 작성**

Create `tests/test_sim.py`:
```python
"""sim 모듈 단위 테스트."""

from agent import sim


def test_current_mode_defaults_to_stable_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(sim, "MODE_PATH", str(tmp_path / "absent"))
    monkeypatch.setattr(sim, "DEFAULT_MODE", "stable")
    assert sim.current_mode() == "stable"


def test_current_mode_reads_valid_file(tmp_path, monkeypatch):
    path = tmp_path / "mode"
    path.write_text("real\n")
    monkeypatch.setattr(sim, "MODE_PATH", str(path))
    assert sim.current_mode() == "real"


def test_current_mode_rejects_unknown(tmp_path, monkeypatch):
    path = tmp_path / "mode"
    path.write_text("bogus")
    monkeypatch.setattr(sim, "MODE_PATH", str(path))
    monkeypatch.setattr(sim, "DEFAULT_MODE", "stable")
    assert sim.current_mode() == "stable"


def test_read_pct_file_clamps_and_validates(tmp_path):
    good = tmp_path / "g"
    good.write_text("73.5")
    assert sim.read_pct_file(str(good)) == 73.5
    bad = tmp_path / "b"
    bad.write_text("150")
    assert sim.read_pct_file(str(bad)) is None
    assert sim.read_pct_file(str(tmp_path / "absent")) is None


def test_mean_revert_stays_in_bounds_and_near_baseline():
    s = sim.MeanRevertSim("cpu:1", baseline=80.0, low=5.0, high=95.0)
    values = [s.step(80.0) for _ in range(200)]
    assert all(5.0 <= v <= 95.0 for v in values)
    # 평균회귀이므로 장기 평균이 기준선 근처에 머문다.
    assert 65.0 <= (sum(values) / len(values)) <= 95.0


def test_mean_revert_is_deterministic():
    a = sim.MeanRevertSim("cpu:1", 50.0, 5.0, 95.0)
    b = sim.MeanRevertSim("cpu:1", 50.0, 5.0, 95.0)
    assert [a.step(50.0) for _ in range(10)] == [b.step(50.0) for _ in range(10)]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_sim.py -v`
Expected: FAIL (`ModuleNotFoundError: agent.sim`)

- [ ] **Step 3: 구현**

Create `agent/sim.py`:
```python
"""모드 판정·공용 파일 리더·평균회귀 시뮬.

collectors가 공유한다. 모드는 /tmp/agent_mode 한 줄로 정하며, 없으면 config.DEFAULT_MODE.
override·baseline 파일 리더를 한곳에 모아 수집기 간 중복을 없앤다. MeanRevertSim은 기준선
중심으로 0.5~2%씩 흔들리는 안정 곡선을 만든다(데모 기본 모드).
"""

import hashlib
import random

from agent.config import DEFAULT_MODE

MODE_PATH = "/tmp/agent_mode"
VALID_MODES = ("stable", "real", "randomwalk")


def current_mode() -> str:
    """컨테이너 모드. 파일이 없거나 알 수 없는 값이면 DEFAULT_MODE."""
    try:
        with open(MODE_PATH) as f:
            mode = f.read().strip()
    except OSError:
        return DEFAULT_MODE
    return mode if mode in VALID_MODES else DEFAULT_MODE


def read_pct_file(path: str) -> float | None:
    """0~100 백분율 파일을 읽는다. 없거나 범위를 벗어나면 None."""
    try:
        with open(path) as f:
            value = float(f.read().strip())
    except (OSError, ValueError):
        return None
    if 0.0 <= value <= 100.0:
        return round(value, 1)
    return None


def seeded_rng(key: str) -> random.Random:
    """문자열 키를 SHA-256 해시해 결정론적 RNG를 만든다."""
    return random.Random(int(hashlib.sha256(key.encode()).hexdigest(), 16))


class MeanRevertSim:
    """기준선 중심 평균회귀. 매 step마다 0.5~2% 흔들리며 기준선으로 당겨진다."""

    PULL = 0.15

    def __init__(self, seed_key: str, baseline: float, low: float, high: float) -> None:
        self._rng = seeded_rng(seed_key)
        self._low = low
        self._high = high
        self._value = baseline

    def step(self, baseline: float) -> float:
        """다음 값. baseline은 런타임에 바뀔 수 있어 매번 받는다."""
        move = self._rng.uniform(0.5, 2.0) * self._rng.choice((-1.0, 1.0))
        pull = (baseline - self._value) * self.PULL
        self._value = max(self._low, min(self._high, self._value + move + pull))
        return round(self._value, 1)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_sim.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: 커밋**

```bash
git add agent/sim.py tests/test_sim.py
git commit -m "feat: agent sim 모듈(모드 판정·공용 리더·평균회귀)"
```

---

## Task 2: config.py — DEFAULT_MODE 도입

**Files:**
- Modify: `agent/config.py` (마지막 `METRIC_SIMULATE` 블록 교체)

- [ ] **Step 1: 구현 (테스트는 Task 3~6에서 모드로 검증)**

`agent/config.py`에서 아래 블록을 찾는다:
```python
# CPU·메모리 시뮬레이션: 컨테이너는 호스트 /proc를 공유하므로 psutil 실측값이
# 모든 에이전트에서 동일하게 나온다. 기본 활성화해 서버마다 다른 곡선을 유지한다.
# 실제 베어메탈 배포 시 METRIC_SIMULATE=false로 끄면 psutil 실측값으로 전환된다.
METRIC_SIMULATE = os.getenv("METRIC_SIMULATE", "true").lower() == "true"
```
다음으로 교체한다:
```python
# 기본 모드: 모드 파일(/tmp/agent_mode)이 없을 때 적용한다.
# stable=안정 합성(데모 기본), real=psutil 실측, randomwalk=±8% 랜덤워크.
# 베어메탈 실측 배포는 DEFAULT_MODE=real.
DEFAULT_MODE = os.getenv("DEFAULT_MODE", "stable")
```

- [ ] **Step 2: import 깨짐 없는지 확인**

Run: `uv run python -c "from agent import config, sim; print(config.DEFAULT_MODE)"`
Expected: `stable`

- [ ] **Step 3: 커밋**

```bash
git add agent/config.py
git commit -m "feat: METRIC_SIMULATE를 DEFAULT_MODE로 대체"
```

---

## Task 3: cpu.py — 우선순위 재작성

**Files:**
- Modify: `agent/collectors/cpu.py` (전체 교체)
- Test: `tests/test_collectors.py` (추가)

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_collectors.py` 끝에 추가:
```python
from agent import sim as sim_mod


def test_cpu_override_wins_in_every_mode(tmp_path, monkeypatch):
    override = tmp_path / "cpu_ov"
    override.write_text("88.0")
    mode_file = tmp_path / "mode"
    monkeypatch.setattr(cpu_mod, "CPU_OVERRIDE_PATH", str(override))
    monkeypatch.setattr(sim_mod, "MODE_PATH", str(mode_file))
    for mode in ("stable", "real", "randomwalk"):
        mode_file.write_text(mode)
        assert cpu_mod.read_cpu_usage() == 88.0


def test_cpu_stable_uses_baseline_and_stays_in_range(tmp_path, monkeypatch):
    baseline = tmp_path / "cpu_base"
    baseline.write_text("80")
    monkeypatch.setattr(cpu_mod, "CPU_BASELINE_PATH", str(baseline))
    monkeypatch.setattr(cpu_mod, "CPU_OVERRIDE_PATH", str(tmp_path / "absent"))
    monkeypatch.setattr(sim_mod, "MODE_PATH", str(tmp_path / "absent"))
    monkeypatch.setattr(sim_mod, "DEFAULT_MODE", "stable")
    values = [cpu_mod.read_cpu_usage() for _ in range(150)]
    assert all(5.0 <= v <= 95.0 for v in values)
    assert 60.0 <= (sum(values) / len(values)) <= 95.0
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_collectors.py::test_cpu_override_wins_in_every_mode -v`
Expected: FAIL (`AttributeError: ... CPU_BASELINE_PATH` 또는 기존 동작 불일치)

- [ ] **Step 3: 구현 — `agent/collectors/cpu.py` 전체 교체**

```python
"""CPU 사용률 수집기."""

import psutil

from agent import sim
from agent.config import SERVER_ID

CPU_OVERRIDE_PATH = "/tmp/agent_cpu_override"
CPU_BASELINE_PATH = "/tmp/agent_cpu_baseline"

_LOW, _HIGH = 5.0, 95.0
_SEED_BASELINE = sim.seeded_rng(f"cpu:{SERVER_ID}").uniform(5.0, 70.0)
_stable = sim.MeanRevertSim(f"cpu:{SERVER_ID}", _SEED_BASELINE, _LOW, _HIGH)

# randomwalk 모드용 상태(기존 ±8% 동작 보존).
_walk_rng = sim.seeded_rng(f"cpu:{SERVER_ID}")
_walk = _walk_rng.uniform(5.0, 70.0)


def read_cpu_usage() -> float:
    """현재 CPU 사용률(%). 우선순위: override > stable > real > randomwalk."""
    global _walk
    override = sim.read_pct_file(CPU_OVERRIDE_PATH)
    if override is not None:
        return override
    mode = sim.current_mode()
    if mode == "real":
        return psutil.cpu_percent(interval=None)
    if mode == "randomwalk":
        _walk = max(_LOW, min(_HIGH, _walk + _walk_rng.uniform(-8.0, 8.0)))
        return round(_walk, 1)
    baseline = sim.read_pct_file(CPU_BASELINE_PATH)
    return _stable.step(baseline if baseline is not None else _SEED_BASELINE)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_collectors.py -v`
Expected: PASS (기존 + 신규 모두)

- [ ] **Step 5: 커밋**

```bash
git add agent/collectors/cpu.py tests/test_collectors.py
git commit -m "feat: cpu 수집기 모드 우선순위 재작성"
```

---

## Task 4: memory.py — 우선순위 재작성

**Files:**
- Modify: `agent/collectors/memory.py` (전체 교체)
- Test: `tests/test_collectors.py` (추가)

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_collectors.py` 끝에 추가:
```python
def test_mem_override_wins(tmp_path, monkeypatch):
    override = tmp_path / "mem_ov"
    override.write_text("55.0")
    monkeypatch.setattr(mem_mod, "MEM_OVERRIDE_PATH", str(override))
    monkeypatch.setattr(sim_mod, "MODE_PATH", str(tmp_path / "absent"))
    assert mem_mod.read_mem_usage() == 55.0


def test_mem_stable_in_range(tmp_path, monkeypatch):
    monkeypatch.setattr(mem_mod, "MEM_OVERRIDE_PATH", str(tmp_path / "absent"))
    monkeypatch.setattr(mem_mod, "MEM_BASELINE_PATH", str(tmp_path / "absent"))
    monkeypatch.setattr(sim_mod, "MODE_PATH", str(tmp_path / "absent"))
    monkeypatch.setattr(sim_mod, "DEFAULT_MODE", "stable")
    values = [mem_mod.read_mem_usage() for _ in range(120)]
    assert all(10.0 <= v <= 90.0 for v in values)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_collectors.py::test_mem_stable_in_range -v`
Expected: FAIL (`AttributeError: MEM_BASELINE_PATH`)

- [ ] **Step 3: 구현 — `agent/collectors/memory.py` 전체 교체**

```python
"""메모리 사용률 수집기."""

import psutil

from agent import sim
from agent.config import SERVER_ID

MEM_OVERRIDE_PATH = "/tmp/agent_mem_override"
MEM_BASELINE_PATH = "/tmp/agent_mem_baseline"

_LOW, _HIGH = 10.0, 90.0
_SEED_BASELINE = sim.seeded_rng(f"mem:{SERVER_ID}").uniform(20.0, 75.0)
_stable = sim.MeanRevertSim(f"mem:{SERVER_ID}", _SEED_BASELINE, _LOW, _HIGH)

# randomwalk 모드용 상태(기존 ±3% 동작 보존).
_walk_rng = sim.seeded_rng(f"mem:{SERVER_ID}")
_walk = _walk_rng.uniform(20.0, 75.0)


def read_mem_usage() -> float:
    """현재 메모리 사용률(%). 우선순위: override > stable > real > randomwalk."""
    global _walk
    override = sim.read_pct_file(MEM_OVERRIDE_PATH)
    if override is not None:
        return override
    mode = sim.current_mode()
    if mode == "real":
        return psutil.virtual_memory().percent
    if mode == "randomwalk":
        _walk = max(_LOW, min(_HIGH, _walk + _walk_rng.uniform(-3.0, 3.0)))
        return round(_walk, 1)
    baseline = sim.read_pct_file(MEM_BASELINE_PATH)
    return _stable.step(baseline if baseline is not None else _SEED_BASELINE)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_collectors.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add agent/collectors/memory.py tests/test_collectors.py
git commit -m "feat: memory 수집기 모드 우선순위 재작성"
```

---

## Task 5: gpu.py — 우선순위 재작성

**Files:**
- Modify: `agent/collectors/gpu.py` (전체 교체)
- Test: `tests/test_collectors.py` (추가)

GPU는 컨테이너에 실제 텔레메트리가 없다. `real` 모드는 None을 반환한다(실제 GPU 노드 연동은 후속 과제). GPU 미탑재 서버(`GPU_SIMULATE=False`)는 항상 None.

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_collectors.py` 끝에 추가:
```python
def test_gpu_real_mode_returns_none(tmp_path, monkeypatch):
    mode_file = tmp_path / "mode"
    mode_file.write_text("real")
    monkeypatch.setattr(sim_mod, "MODE_PATH", str(mode_file))
    monkeypatch.setattr(gpu_mod, "GPU_SIMULATE", True)
    monkeypatch.setattr(gpu_mod, "GPU_OVERRIDE_PATH", str(tmp_path / "absent"))
    assert gpu_mod.read_gpu_usage() is None


def test_gpu_disabled_always_none(tmp_path, monkeypatch):
    monkeypatch.setattr(gpu_mod, "GPU_SIMULATE", False)
    monkeypatch.setattr(sim_mod, "MODE_PATH", str(tmp_path / "absent"))
    assert gpu_mod.read_gpu_usage() is None


def test_gpu_stable_in_range(tmp_path, monkeypatch):
    monkeypatch.setattr(gpu_mod, "GPU_SIMULATE", True)
    monkeypatch.setattr(gpu_mod, "GPU_OVERRIDE_PATH", str(tmp_path / "absent"))
    monkeypatch.setattr(gpu_mod, "GPU_BASELINE_PATH", str(tmp_path / "absent"))
    monkeypatch.setattr(sim_mod, "MODE_PATH", str(tmp_path / "absent"))
    monkeypatch.setattr(sim_mod, "DEFAULT_MODE", "stable")
    values = [gpu_mod.read_gpu_usage() for _ in range(120)]
    assert all(v is not None and 0.0 <= v <= 100.0 for v in values)
```

기존 테스트 `test_gpu_override_returns_file_value`, `test_gpu_override_ignored_when_out_of_range`는 그대로 통과해야 한다(override 경로 유지).

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_collectors.py::test_gpu_real_mode_returns_none -v`
Expected: FAIL

- [ ] **Step 3: 구현 — `agent/collectors/gpu.py` 전체 교체**

```python
"""GPU 사용률 수집기.

컨테이너에는 물리 GPU가 없다. GPU_SIMULATE가 켜진 서버만 합성값을 내고, 꺼진 서버는
항상 None(GPU 미탑재). real 모드는 실제 텔레메트리가 없어 None을 반환한다(실 GPU 노드
연동은 후속 과제). override 파일이 있으면 모든 모드에서 그 값을 우선한다(테스트 툴 주입용).
"""

from agent import sim
from agent.config import GPU_SIMULATE, SERVER_ID

GPU_OVERRIDE_PATH = "/tmp/agent_gpu_override"
GPU_BASELINE_PATH = "/tmp/agent_gpu_baseline"

_LOW, _HIGH = 0.0, 100.0
_SEED_BASELINE = sim.seeded_rng(f"gpu:{SERVER_ID}").uniform(20.0, 80.0)
_stable = sim.MeanRevertSim(f"gpu:{SERVER_ID}", _SEED_BASELINE, _LOW, _HIGH)

# randomwalk 모드용 상태(기존 ±5% 동작 보존).
_walk_rng = sim.seeded_rng(f"gpu:{SERVER_ID}")
_walk = _walk_rng.uniform(20.0, 80.0)


def read_gpu_usage() -> float | None:
    """GPU 사용률(%). GPU 미탑재/real 모드는 None."""
    global _walk
    if not GPU_SIMULATE:
        return None
    override = sim.read_pct_file(GPU_OVERRIDE_PATH)
    if override is not None:
        return override
    mode = sim.current_mode()
    if mode == "real":
        return None
    if mode == "randomwalk":
        _walk = max(_LOW, min(_HIGH, _walk + _walk_rng.uniform(-5.0, 5.0)))
        return round(_walk, 1)
    baseline = sim.read_pct_file(GPU_BASELINE_PATH)
    return _stable.step(baseline if baseline is not None else _SEED_BASELINE)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_collectors.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add agent/collectors/gpu.py tests/test_collectors.py
git commit -m "feat: gpu 수집기 모드 우선순위 재작성"
```

---

## Task 6: net.py — 우선순위 재작성

**Files:**
- Modify: `agent/collectors/net.py` (전체 교체)
- Test: `tests/test_collectors.py` (추가)

`real` 모드만 psutil throughput을 계산한다(기존 로직). stable/randomwalk는 합성값.

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_collectors.py` 끝에 추가:
```python
import agent.collectors.net as net_mod


def test_net_override_wins(tmp_path, monkeypatch):
    override = tmp_path / "net_ov"
    override.write_text("33.0")
    monkeypatch.setattr(net_mod, "NET_OVERRIDE_PATH", str(override))
    monkeypatch.setattr(sim_mod, "MODE_PATH", str(tmp_path / "absent"))
    assert net_mod.read_net_usage() == 33.0


def test_net_stable_in_range(tmp_path, monkeypatch):
    monkeypatch.setattr(net_mod, "NET_OVERRIDE_PATH", str(tmp_path / "absent"))
    monkeypatch.setattr(net_mod, "NET_BASELINE_PATH", str(tmp_path / "absent"))
    monkeypatch.setattr(sim_mod, "MODE_PATH", str(tmp_path / "absent"))
    monkeypatch.setattr(sim_mod, "DEFAULT_MODE", "stable")
    values = [net_mod.read_net_usage() for _ in range(120)]
    assert all(0.0 <= v <= 100.0 for v in values)
```

기존 `test_net_usage_in_range`는 real 모드 경로를 타지 않으면 첫 호출 0.0 가정이 깨질 수 있으니, 그 테스트를 real 모드로 고정하도록 함께 수정한다:
```python
def test_net_usage_in_range(monkeypatch) -> None:
    import agent.collectors.net as net_mod
    from agent import sim as sim_mod
    monkeypatch.setattr(sim_mod, "current_mode", lambda: "real")
    net_mod._last_sample = None
    read_net_usage()  # 첫 호출은 기준점만 잡는다.
    value = read_net_usage()
    assert isinstance(value, float)
    assert 0.0 <= value <= 100.0
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_collectors.py::test_net_stable_in_range -v`
Expected: FAIL

- [ ] **Step 3: 구현 — `agent/collectors/net.py` 전체 교체**

```python
"""네트워크 사용률 수집기.

real 모드는 NIC 대역폭(NET_CAP_MBPS) 대비 순간 처리량을 계산한다. psutil은 누적
바이트만 주므로 직전 표본과의 증가분/경과 시간으로 throughput을 구한다. stable/randomwalk
모드는 합성값을 낸다. override 파일이 있으면 모든 모드에서 우선한다.
"""

import time

import psutil

from agent import sim
from agent.config import NET_CAP_MBPS, SERVER_ID

NET_OVERRIDE_PATH = "/tmp/agent_net_override"
NET_BASELINE_PATH = "/tmp/agent_net_baseline"

_LOW, _HIGH = 0.0, 100.0
_SEED_BASELINE = sim.seeded_rng(f"net:{SERVER_ID}").uniform(2.0, 30.0)
_stable = sim.MeanRevertSim(f"net:{SERVER_ID}", _SEED_BASELINE, _LOW, _HIGH)

_walk_rng = sim.seeded_rng(f"net:{SERVER_ID}")
_walk = _walk_rng.uniform(2.0, 30.0)

# (monotonic 시각, 누적 송수신 바이트). real 모드 첫 호출 전에는 None.
_last_sample: tuple[float, int] | None = None


def _read_real() -> float:
    """psutil 누적 바이트 증가분으로 NIC 대역폭 대비 사용률(%)을 계산한다."""
    global _last_sample
    counters = psutil.net_io_counters()
    total_bytes = counters.bytes_sent + counters.bytes_recv
    now = time.monotonic()
    if _last_sample is None:
        _last_sample = (now, total_bytes)
        return 0.0
    last_time, last_bytes = _last_sample
    _last_sample = (now, total_bytes)
    elapsed = now - last_time
    if elapsed <= 0:
        return 0.0
    mbps = (total_bytes - last_bytes) * 8 / 1_000_000 / elapsed
    return round(min(100.0, mbps / NET_CAP_MBPS * 100), 1)


def read_net_usage() -> float:
    """네트워크 사용률(%). 우선순위: override > stable > real > randomwalk."""
    global _walk
    override = sim.read_pct_file(NET_OVERRIDE_PATH)
    if override is not None:
        return override
    mode = sim.current_mode()
    if mode == "real":
        return _read_real()
    if mode == "randomwalk":
        _walk = max(_LOW, min(_HIGH, _walk + _walk_rng.uniform(-4.0, 4.0)))
        return round(_walk, 1)
    baseline = sim.read_pct_file(NET_BASELINE_PATH)
    return _stable.step(baseline if baseline is not None else _SEED_BASELINE)
```

- [ ] **Step 4: 전체 agent 테스트 통과 확인**

Run: `uv run pytest -m "not integration" -v`
Expected: PASS (전부)

- [ ] **Step 5: 커밋**

```bash
git add agent/collectors/net.py tests/test_collectors.py
git commit -m "feat: net 수집기 모드 우선순위 재작성"
```

---

## Task 7: testtool config.py — 경로 추가

**Files:**
- Modify: `testtool/app/config.py`

- [ ] **Step 1: 구현**

`testtool/app/config.py`의 override 경로 블록 아래에 추가:
```python
# 모드 토글 파일(agent/sim.py와 동일 경로).
MODE_PATH = "/tmp/agent_mode"
NET_OVERRIDE_PATH = "/tmp/agent_net_override"

# 자원별 기준선(시드) 파일(stable 모드 중심값).
CPU_BASELINE_PATH = "/tmp/agent_cpu_baseline"
MEM_BASELINE_PATH = "/tmp/agent_mem_baseline"
GPU_BASELINE_PATH = "/tmp/agent_gpu_baseline"
NET_BASELINE_PATH = "/tmp/agent_net_baseline"
```

- [ ] **Step 2: import 확인**

Run (in `testtool/`): `uv run python -c "from app import config; print(config.MODE_PATH, config.CPU_BASELINE_PATH)"`
Expected: `/tmp/agent_mode /tmp/agent_cpu_baseline`

- [ ] **Step 3: 커밋**

```bash
git add testtool/app/config.py
git commit -m "feat: testtool 모드·기준선·net 경로 추가"
```

---

## Task 8: sim_control.py — 모드·기준선 제어

**Files:**
- Create: `testtool/app/sim_control.py`
- Test: `testtool/tests/test_sim_control.py`

- [ ] **Step 1: 실패하는 테스트 작성**

Create `testtool/tests/test_sim_control.py`:
```python
import pytest

from app import config, sim_control


def test_build_set_mode_cmd_valid():
    cmd = sim_control.build_set_mode_cmd("real")
    assert cmd == ["sh", "-c", f"echo real > {config.MODE_PATH}"]


def test_build_set_mode_cmd_rejects_unknown():
    with pytest.raises(ValueError):
        sim_control.build_set_mode_cmd("bogus")


def test_build_set_baseline_cmd_clamps():
    cmd = sim_control.build_set_baseline_cmd(config.CPU_BASELINE_PATH, 150)
    assert cmd == ["sh", "-c", f"echo 100 > {config.CPU_BASELINE_PATH}"]


def test_build_clear_cmd():
    assert sim_control.build_clear_cmd(config.MODE_PATH) == ["rm", "-f", config.MODE_PATH]
```

- [ ] **Step 2: 테스트 실패 확인**

Run (in `testtool/`): `uv run pytest tests/test_sim_control.py -v`
Expected: FAIL (`ModuleNotFoundError: app.sim_control`)

- [ ] **Step 3: 구현**

Create `testtool/app/sim_control.py`:
```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run (in `testtool/`): `uv run pytest tests/test_sim_control.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 커밋**

```bash
git add testtool/app/sim_control.py testtool/tests/test_sim_control.py
git commit -m "feat: testtool sim_control(모드·기준선 docker exec 제어)"
```

---

## Task 9: load_injector.py — net 주입 추가

**Files:**
- Modify: `testtool/app/load_injector.py`
- Test: `testtool/tests/test_load_injector.py` (없으면 생성, 있으면 추가)

- [ ] **Step 1: 실패하는 테스트 작성/추가**

`testtool/tests/test_load_injector.py`에 추가(파일 없으면 생성하고 상단에 `from app import config, load_injector` 추가):
```python
from app import config, load_injector


def test_build_set_cmd_for_net():
    cmd = load_injector.build_set_cmd(config.NET_OVERRIDE_PATH, 70)
    assert cmd == ["sh", "-c", f"echo 70 > {config.NET_OVERRIDE_PATH}"]
```

- [ ] **Step 2: 테스트 실패 확인 (혹은 회귀 확인)**

Run (in `testtool/`): `uv run pytest tests/test_load_injector.py -v`
Expected: 새 테스트 PASS 가능(build_set_cmd 재사용). 핵심은 Step 3에서 apply_net 추가.

- [ ] **Step 3: 구현 — `LoadInjector`에 net 메서드 추가**

`testtool/app/load_injector.py`의 `set_gpu`/`clear_gpu` 다음에 추가:
```python
    def apply_net(self, server_id: int, pct: int) -> None:
        self._docker.exec_run(server_id, build_set_cmd(config.NET_OVERRIDE_PATH, pct))

    def clear_net(self, server_id: int) -> None:
        self._docker.exec_run(server_id, build_clear_cmd(config.NET_OVERRIDE_PATH))
```

같은 파일 `revert_all`의 루프에 `self.clear_net`을 포함하도록 수정:
```python
    def revert_all(self, server_id: int) -> None:
        """한 서버의 CPU/RAM/GPU/Net 오버라이드를 모두 지운다. 개별 실패는 무시."""
        for fn in (self.clear_cpu, self.clear_ram, self.clear_gpu, self.clear_net):
            try:
                fn(server_id)
            except Exception:
                pass
```

- [ ] **Step 4: 테스트 통과 확인**

Run (in `testtool/`): `uv run pytest tests/ -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add testtool/app/load_injector.py testtool/tests/test_load_injector.py
git commit -m "feat: testtool net 부하 주입·revert_all에 net 포함"
```

---

## Task 10: scenarios.py — 실무형 카오스 2종 + load_net dispatch

**Files:**
- Modify: `testtool/app/scenarios.py`
- Test: `testtool/tests/test_scenarios.py` (없으면 생성)

- [ ] **Step 1: 실패하는 테스트 작성**

Create/append `testtool/tests/test_scenarios.py`:
```python
import random

from app.scenarios import CascadingFailure, MemoryLeak


def test_memory_leak_ramps_then_oom():
    eng = MemoryLeak([1, 2], duration_s=10, start_pct=40, max_pct=99, oom_hold_s=3)
    rng = random.Random(0)
    running = {1, 2}
    # 초반: 대상 선택 + load_ram 상승
    a0 = eng.tick(0, running, rng)
    kinds0 = [x.kind for x in a0]
    assert "load_ram" in kinds0
    target = a0[0].server_id
    # 램프 진행 중 값이 단조 증가
    v1 = next(x.value for x in eng.tick(2, running, rng) if x.kind == "load_ram")
    v2 = next(x.value for x in eng.tick(6, running, rng) if x.kind == "load_ram")
    assert v2 > v1
    # 임계 도달 시 stop 발생
    acts = eng.tick(10, running, rng)
    assert any(x.kind == "stop" and x.server_id == target for x in acts)


def test_memory_leak_done_after_restart():
    eng = MemoryLeak([1], duration_s=4, start_pct=40, max_pct=99, oom_hold_s=2)
    rng = random.Random(0)
    running = {1}
    for t in range(0, 5):
        eng.tick(t, running, rng)
    # oom_hold 경과 후 start+revert, done
    later = eng.tick(20, running, rng)
    assert any(x.kind == "start" for x in later)
    assert eng.is_done(20)


def test_cascading_starts_with_a_stop():
    eng = CascadingFailure([1, 2, 3], duration_s=30, step_every_s=5)
    rng = random.Random(1)
    acts = eng.tick(0, {1, 2, 3}, rng)
    assert len(acts) == 1 and acts[0].kind == "stop"


def test_cascading_loads_remaining_servers():
    eng = CascadingFailure([1, 2, 3], duration_s=30, step_every_s=5)
    rng = random.Random(1)
    eng.tick(0, {1, 2, 3}, rng)          # 한 대 정지
    acts = eng.tick(5, {1, 2, 3}, rng)   # 나머지 부하
    loaded = {x.server_id for x in acts if x.kind in ("load_cpu", "load_ram")}
    assert len(loaded) >= 1


def test_cascading_reverts_after_duration():
    eng = CascadingFailure([1, 2], duration_s=10, step_every_s=5)
    rng = random.Random(1)
    eng.tick(0, {1, 2}, rng)
    acts = eng.tick(10, {1, 2}, rng)
    assert any(x.kind == "revert" for x in acts)
    assert eng.is_done(10)
```

- [ ] **Step 2: 테스트 실패 확인**

Run (in `testtool/`): `uv run pytest tests/test_scenarios.py -v`
Expected: FAIL (`ImportError: cannot import name 'MemoryLeak'`)

- [ ] **Step 3: 구현 — `testtool/app/scenarios.py`에 두 엔진 추가**

`RandomSpike` 클래스 정의 다음, `from PyQt6...` import 줄 **앞에** 추가:
```python
class MemoryLeak:
    """대상 1대의 RAM을 start_pct→max_pct로 duration 동안 선형 상승.
    임계 도달 시 stop(OOM 모사)→oom_hold초 뒤 start·revert.
    """

    def __init__(self, server_ids, duration_s, start_pct=40, max_pct=99, oom_hold_s=8):
        self._ids = list(server_ids)
        self._duration = max(1, duration_s)
        self._start = start_pct
        self._max = max_pct
        self._oom_hold = oom_hold_s
        self._target = None
        self._restart_at = None
        self._oom = False
        self._done = False

    def tick(self, elapsed_s, running, rng):
        actions = []
        if self._target is None:
            candidates = [s for s in self._ids if s in running]
            if not candidates:
                return []
            self._target = rng.choice(candidates)
        if self._restart_at is not None:
            if elapsed_s >= self._restart_at:
                self._restart_at = None
                self._done = True
                return [Action("start", self._target), Action("revert", self._target)]
            return []
        if self._oom:
            return []
        ramp = min(1.0, elapsed_s / self._duration)
        pct = int(self._start + (self._max - self._start) * ramp)
        actions.append(Action("load_ram", self._target, pct))
        if pct >= self._max:
            self._oom = True
            self._restart_at = elapsed_s + self._oom_hold
            actions.append(Action("stop", self._target, self._oom_hold))
        return actions

    def is_done(self, elapsed_s):
        return self._done


class CascadingFailure:
    """1대 정지로 시작, 남은 서버 CPU/RAM을 step_every_s마다 단계적으로 상승(부하 재분배).
    duration 만료 시 전체 revert·정지 서버 start.
    """

    def __init__(self, server_ids, duration_s, step_every_s=8,
                 base_pct=55, step_pct=12, max_pct=98):
        self._ids = list(server_ids)
        self._duration = duration_s
        self._every = max(1, step_every_s)
        self._base = base_pct
        self._step = step_pct
        self._max = max_pct
        self._downed = None
        self._reverted = False

    def tick(self, elapsed_s, running, rng):
        if elapsed_s >= self._duration:
            if self._reverted:
                return []
            self._reverted = True
            acts = [Action("revert", s) for s in self._ids]
            if self._downed is not None:
                acts.append(Action("start", self._downed))
            return acts
        if self._downed is None:
            candidates = [s for s in self._ids if s in running]
            if not candidates:
                return []
            self._downed = rng.choice(candidates)
            return [Action("stop", self._downed)]
        actions = []
        if elapsed_s > 0 and elapsed_s % self._every == 0:
            stage = elapsed_s // self._every
            pct = min(self._max, self._base + self._step * (stage - 1))
            for s in self._ids:
                if s != self._downed and s in running:
                    actions.append(Action("load_cpu", s, pct))
                    actions.append(Action("load_ram", s, pct))
        return actions

    def is_done(self, elapsed_s):
        return elapsed_s >= self._duration and self._reverted
```

같은 파일 `ChaosRunner._dispatch`의 `elif a.kind == "gpu":` 블록 다음에 추가:
```python
        elif a.kind == "load_net":
            pct = int(a.value)
            self._run_async(lambda s=sid, v=pct: self._injector.apply_net(s, v))
            self.log.emit(f"agent-{sid} NET {pct}% 부하 주입")
```

- [ ] **Step 4: 테스트 통과 확인**

Run (in `testtool/`): `uv run pytest tests/test_scenarios.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add testtool/app/scenarios.py testtool/tests/test_scenarios.py
git commit -m "feat: 카오스 시나리오 메모리 누수·연쇄 장애 추가"
```

---

## Task 11: theme.py — 다크 모던 QSS

**Files:**
- Create: `testtool/app/ui/theme.py`

순수 상수·문자열이라 단위 테스트 없이 import만 검증한다.

- [ ] **Step 1: 구현**

Create `testtool/app/ui/theme.py`:
```python
"""다크 모던 테마: 전역 QSS와 메트릭 임계 색상.

main.py에서 app.setStyleSheet(STYLESHEET)로 적용한다. 색은 한곳에서 관리한다.
"""

BG = "#15171c"
SURFACE = "#1e2128"
SURFACE_HI = "#242832"
BORDER = "#2c313c"
TEXT = "#e6e8ec"
MUTED = "#9aa0aa"
ACCENT = "#4f9cf9"
ACCENT_HI = "#6cb0ff"

# 메트릭 임계 색상.
OK = "#3ddc97"
WARN = "#f5a623"
CRIT = "#ff5c5c"


def level_color(value) -> str:
    """사용률 값에 따른 색. None이면 뮤트."""
    if value is None:
        return MUTED
    if value >= 90:
        return CRIT
    if value >= 70:
        return WARN
    return OK


STYLESHEET = f"""
* {{
    font-family: "Pretendard", "Noto Sans KR", "Segoe UI", sans-serif;
    font-size: 13px;
    color: {TEXT};
}}
QWidget {{ background: {BG}; }}
QGroupBox {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
    margin-top: 14px;
    padding: 12px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: {MUTED};
    font-weight: 600;
}}
QPushButton {{
    background: {SURFACE_HI};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px 12px;
}}
QPushButton:hover {{ background: {BORDER}; border-color: {ACCENT}; }}
QPushButton:pressed {{ background: {ACCENT}; color: #0c0e12; }}
QComboBox, QSpinBox {{
    background: {SURFACE_HI};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 4px 8px;
}}
QComboBox:focus, QSpinBox:focus {{ border-color: {ACCENT}; }}
QComboBox QAbstractItemView {{
    background: {SURFACE_HI};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT};
}}
QSlider::groove:horizontal {{
    height: 4px; background: {BORDER}; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {ACCENT}; width: 14px; height: 14px;
    margin: -6px 0; border-radius: 7px;
}}
QTableWidget {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
    gridline-color: {BORDER};
    selection-background-color: {SURFACE_HI};
}}
QHeaderView::section {{
    background: {SURFACE_HI};
    color: {MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 6px;
}}
QPlainTextEdit {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
    color: {MUTED};
}}
QRadioButton {{ spacing: 6px; }}
"""
```

- [ ] **Step 2: import 확인**

Run (in `testtool/`): `uv run python -c "from app.ui import theme; print(theme.level_color(95), theme.level_color(10))"`
Expected: `#ff5c5c #3ddc97`

- [ ] **Step 3: 커밋**

```bash
git add testtool/app/ui/theme.py
git commit -m "feat: testtool 다크 모던 테마"
```

---

## Task 12: sim_panel.py — 모드·기준선 GUI

**Files:**
- Create: `testtool/app/ui/sim_panel.py`

위젯은 시그널만 emit한다. 실행은 main_window가 디스패치(Task 14).

- [ ] **Step 1: 구현**

Create `testtool/app/ui/sim_panel.py`:
```python
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
```

- [ ] **Step 2: import 확인**

Run (in `testtool/`): `uv run python -c "from app.ui.sim_panel import SimPanel; print('ok')"`
Expected: `ok`

- [ ] **Step 3: 커밋**

```bash
git add testtool/app/ui/sim_panel.py
git commit -m "feat: testtool 모드·기준선 제어 패널"
```

---

## Task 13: server_table.py — 임계 색상

**Files:**
- Modify: `testtool/app/ui/server_table.py`

- [ ] **Step 1: 구현 — 메트릭 셀에 색상 적용**

`testtool/app/ui/server_table.py` 상단 import에 추가:
```python
from PyQt6.QtGui import QColor

from app.ui import theme
```

`update_snapshots`를 다음으로 교체(메트릭 셀에 임계 색상 적용):
```python
    def update_snapshots(self, snapshots):
        by_id = {s.server_id: s for s in snapshots}
        for row, sid in enumerate(self._ids):
            snap = by_id.get(sid)
            if snap is None:
                continue
            m = snap.metrics
            self.setItem(row, 1, QTableWidgetItem(snap.status))
            for col, value in enumerate([m.cpu, m.mem, m.gpu, m.net], start=2):
                item = QTableWidgetItem(_fmt(value))
                item.setForeground(QColor(theme.level_color(value)))
                self.setItem(row, col, item)
```

- [ ] **Step 2: import 확인**

Run (in `testtool/`): `uv run python -c "from app.ui.server_table import ServerTable; print('ok')"`
Expected: `ok`

- [ ] **Step 3: 커밋**

```bash
git add testtool/app/ui/server_table.py
git commit -m "feat: 서버 테이블 메트릭 임계 색상"
```

---

## Task 14: 배선 — main_window·scenario_panel·main.py

**Files:**
- Modify: `testtool/app/ui/scenario_panel.py`
- Modify: `testtool/app/ui/main_window.py`
- Modify: `testtool/app/main.py`

- [ ] **Step 1: scenario_panel에 신규 시나리오 추가**

`testtool/app/ui/scenario_panel.py`의 `SCENARIOS`를 교체:
```python
SCENARIOS = ["전체 과부하", "랜덤 정지", "랜덤 부하 스파이크", "메모리 누수", "연쇄 장애"]
```

- [ ] **Step 2: main_window 배선 — SimControl·SimPanel·신규 엔진**

`testtool/app/ui/main_window.py` 수정:

(a) import에 추가:
```python
from app.sim_control import SimControl
from app.ui.sim_panel import SimPanel
```

(b) `__init__`에서 `self._injector = LoadInjector(self._docker)` 다음에:
```python
        self._sim = SimControl(self._docker)
```

(c) 패널 생성부에 `self._sim_panel = SimPanel()`를 추가하고 좌측 레이아웃에 넣는다.
`self._panel = ServerPanel()` 다음 줄에 추가:
```python
        self._sim_panel = SimPanel()
```
`left.addWidget(self._panel)` 다음에 추가:
```python
        left.addWidget(self._sim_panel)
```

(d) 시그널 배선. `self._table.serverSelected.connect(self._panel.set_server)` 다음에 추가:
```python
        self._table.serverSelected.connect(self._sim_panel.set_server)
        self._sim_panel.modeRequested.connect(self._on_mode)
        self._sim_panel.baselineRequested.connect(self._on_baseline)
```

(e) 핸들러 추가. `_on_lifecycle` 메서드 다음에:
```python
    def _on_mode(self, server_id, mode):
        self._run_async(lambda: self._sim.set_mode(server_id, mode))
        self._log.append(f"agent-{server_id} 모드 → {mode}")

    def _on_baseline(self, server_id, resource, value):
        if value is None:
            self._run_async(lambda: self._sim.clear_baseline(server_id, resource))
            self._log.append(f"agent-{server_id} {resource.upper()} 기준선 해제")
        else:
            self._run_async(lambda: self._sim.set_baseline(server_id, resource, value))
            self._log.append(f"agent-{server_id} {resource.upper()} 기준선 {value}%")
```

(f) `_build_engine`에 신규 엔진 추가. `if p["scenario"] == "랜덤 정지":` 블록 다음, `return scenarios.RandomSpike(...)` 앞에:
```python
        if p["scenario"] == "메모리 누수":
            return scenarios.MemoryLeak(ids, duration_s)
        if p["scenario"] == "연쇄 장애":
            return scenarios.CascadingFailure(ids, duration_s)
```

- [ ] **Step 3: main.py에서 테마 적용**

`testtool/app/main.py`에서 `app = QApplication(sys.argv)` 다음에 추가:
```python
    from app.ui.theme import STYLESHEET
    app.setStyleSheet(STYLESHEET)
```

- [ ] **Step 4: import·기존 테스트 회귀 확인**

Run (in `testtool/`):
```bash
uv run python -c "from app.ui.main_window import MainWindow; from app.ui.scenario_panel import SCENARIOS; print(SCENARIOS)"
uv run pytest tests/ -v
```
Expected: SCENARIOS에 5개 출력, 모든 테스트 PASS. (MainWindow는 docker 연결 없이 import만 — `from_env`는 `__init__`에서 호출되므로 인스턴스화는 하지 않고 import만 검증)

- [ ] **Step 5: 커밋**

```bash
git add testtool/app/ui/main_window.py testtool/app/ui/scenario_panel.py testtool/app/main.py
git commit -m "feat: testtool 모드·기준선 패널 배선·신규 시나리오·테마 적용"
```

---

## Task 15: 문서 갱신

**Files:**
- Modify: `tree.md`, `README.md`, `testtool/README.md`, 루트 `../CLAUDE.md`

- [ ] **Step 1: server-pool/tree.md 갱신**

`agent/` 트리에 `sim.py` 추가, `config.py` 설명을 `DEFAULT_MODE`로 갱신. collectors 설명에
"모드(override>stable>real>randomwalk) 우선순위" 한 줄 반영. `testtool/app/` 트리에
`sim_control.py`, `ui/sim_panel.py`, `ui/theme.py` 추가. 하단 설계 원칙의
"CPU/RAM/GPU 제어는 docker exec로 오버라이드 파일을 써서" 문장에 모드·기준선 파일도 같은
방식임을 한 줄 덧붙인다.

- [ ] **Step 2: server-pool/README.md 갱신**

모드 모델 표(stable/real/randomwalk), `/tmp/agent_mode` 토글 예시, 기준선 파일,
`DEFAULT_MODE` 환경변수를 추가한다. 예시:
```bash
# 한 컨테이너를 실측 모드로 전환
docker compose exec agent-3 sh -c 'echo real > /tmp/agent_mode'
# 다시 기본(stable)으로
docker compose exec agent-3 rm -f /tmp/agent_mode
# CPU 기준선 80%로 지정(stable 모드 중심값)
docker compose exec agent-3 sh -c 'echo 80 > /tmp/agent_cpu_baseline'
```

- [ ] **Step 3: testtool/README.md 갱신**

"기능"에 모드 토글·자원별 기준선·신규 카오스(메모리 누수, 연쇄 장애)·다크 테마를 추가.
"동작 방식"에 모드/기준선 파일 docker exec 설명을 추가.

- [ ] **Step 4: 루트 CLAUDE.md 갱신**

`server-pool/` 관련 환경변수 표·설명에서 `GPU_SIMULATE` 옆에 `DEFAULT_MODE`를 추가하고,
"`METRIC_SIMULATE`" 언급이 있으면 모드 모델 설명으로 교체한다. (루트 CLAUDE.md의 Server-Pool
Metrics Contract JSON은 변경 없음.)

- [ ] **Step 5: 커밋**

```bash
git add tree.md README.md testtool/README.md ../CLAUDE.md
git commit -m "docs: 듀얼 모드·기준선·신규 시나리오·테마 문서 반영"
```

참고: 루트 `CLAUDE.md`는 git 제외 대상일 수 있다(프로젝트 메모리). `git add ../CLAUDE.md`가
실패하거나 무시되면 건너뛰고 나머지만 커밋한다.

---

## Task 16: 전체 검증

- [ ] **Step 1: agent 단위 테스트**

Run (in `server-pool/`): `uv run pytest -m "not integration" -v`
Expected: 전부 PASS

- [ ] **Step 2: testtool 테스트**

Run (in `server-pool/testtool/`): `uv run pytest tests/ -v`
Expected: 전부 PASS

- [ ] **Step 3: 에이전트 구동 스모크(선택, docker 필요)**

```bash
docker compose up --build -d
curl -s localhost:9101/metrics
docker compose exec agent-1 sh -c 'echo 80 > /tmp/agent_cpu_baseline'
sleep 6 && curl -s localhost:9101/metrics   # cpuUsage가 80 근처에서 잔잔히 변동
docker compose exec agent-1 sh -c 'echo real > /tmp/agent_mode'
docker compose down
```
Expected: stable에서 cpuUsage가 기준선 근처, mode 전환 동작.

- [ ] **Step 4: 최종 상태 확인**

Run: `git log --oneline feat/dual-mode-sim` 로 커밋 흐름 확인. 푸시는 사용자가 한다(푸시하지 않음).
