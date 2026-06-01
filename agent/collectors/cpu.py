"""CPU 사용률 수집기."""

import psutil


def read_cpu_usage() -> float:
    """현재 CPU 사용률(%)을 반환한다.

    psutil.cpu_percent(interval=None)은 직전 호출 이후의 평균 사용률을 준다.
    /metrics는 주기적으로 PULL되므로 폴링 간격 동안의 사용률이 자연스럽게 잡힌다.
    (첫 호출은 기준점만 잡혀 0.0이 나올 수 있다.)
    """
    return psutil.cpu_percent(interval=None)
