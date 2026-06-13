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
