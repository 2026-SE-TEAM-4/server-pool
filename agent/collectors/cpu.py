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
    """현재 CPU 사용률(%). override가 모든 모드에서 우선. 모드로 real·randomwalk·stable(기본) 중 하나를 디스패치."""
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
