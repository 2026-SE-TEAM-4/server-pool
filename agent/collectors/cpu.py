"""CPU 사용률 수집기."""

import hashlib
import random

import psutil

from agent.config import METRIC_SIMULATE, SERVER_ID

# 테스트 툴이 docker exec로 기록하는 오버라이드 파일 경로.
CPU_OVERRIDE_PATH = "/tmp/agent_cpu_override"

# 네임스페이스 해시로 시드를 만들어 서버 ID가 커질수록 수치도 커지는 단조성을 깬다.
_rng = random.Random(int(hashlib.sha256(f"cpu:{SERVER_ID}".encode()).hexdigest(), 16))
_value = _rng.uniform(5.0, 70.0)


def _read_override() -> float | None:
    """오버라이드 파일 값을 읽는다. 없거나 0~100 밖이면 None."""
    try:
        with open(CPU_OVERRIDE_PATH) as f:
            value = float(f.read().strip())
    except (OSError, ValueError):
        return None
    if 0.0 <= value <= 100.0:
        return round(value, 1)
    return None


def read_cpu_usage() -> float:
    """현재 CPU 사용률(%)을 반환한다.

    테스트 툴이 쓴 오버라이드 파일이 있으면 그 값을 우선한다(시뮬레이션/실측 모두 우선).
    없으면 METRIC_SIMULATE=true(기본)는 SERVER_ID별 랜덤 워크, false는 psutil 실측.
    """
    global _value
    override = _read_override()
    if override is not None:
        return override
    if not METRIC_SIMULATE:
        return psutil.cpu_percent(interval=None)
    # CPU는 메모리보다 변동폭이 크다: ±8%씩 이동, 5~95% 범위.
    _value = max(5.0, min(95.0, _value + _rng.uniform(-8.0, 8.0)))
    return round(_value, 1)
