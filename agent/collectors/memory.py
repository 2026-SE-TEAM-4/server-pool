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
