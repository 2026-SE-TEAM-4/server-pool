"""GPU 사용률 수집기.

시뮬레이션 환경(에이전트 컨테이너)에는 물리 GPU가 없다. 따라서 GPU_SIMULATE가
켜져 있으면 서버별로 다른 합성 사용률을 만들어 대시보드 시연이 의미 있게 하고,
꺼져 있으면 None(GPU 미탑재)을 반환한다. 실제 GPU 노드 연동은 후속 과제다.
"""

import random

from agent import overrides
from agent.config import GPU_SIMULATE, SERVER_ID

# 서버마다 다른 곡선을 그리도록 SERVER_ID로 시드한 난수원. 직전 값 주변에서
# 완만히 움직이는 합성 사용률을 유지한다(0~100 범위).
_rng = random.Random(SERVER_ID)
_value = _rng.uniform(20.0, 80.0)


def read_gpu_usage() -> float | None:
    """GPU 사용률(%)을 반환한다. GPU_SIMULATE가 꺼져 있으면 None."""
    global _value
    if overrides.gpu is not None:
        return overrides.gpu
    if not GPU_SIMULATE:
        return None
    _value = max(0.0, min(100.0, _value + _rng.uniform(-5.0, 5.0)))
    return round(_value, 1)
