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
    """네트워크 사용률(%). override가 모든 모드에서 우선. 모드로 real·randomwalk·stable(기본) 중 하나를 디스패치."""
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
