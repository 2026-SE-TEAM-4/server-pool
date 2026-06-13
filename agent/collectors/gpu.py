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
