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
