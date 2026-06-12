"""CPU 사용률 수집기."""

import random

import psutil

from agent import overrides
from agent.config import SERVER_ID

_rng = random.Random(SERVER_ID)


def read_cpu_usage() -> float:
    """현재 CPU 사용률(%)을 반환한다.

    오버라이드가 주입되어 있으면 해당 값을 그대로 반환한다.
    컨테이너들이 같은 호스트를 공유해 psutil 실측값이 서로 거의 같으므로,
    서버별로 시각적인 구분이 되도록 호스트 실측값에 고유 편차를 더한다.
    """
    if overrides.cpu is not None:
        return overrides.cpu
    base = psutil.cpu_percent(interval=None)
    variance = _rng.uniform(-3.0, 3.0)
    return max(0.0, min(100.0, round(base + variance, 1)))
