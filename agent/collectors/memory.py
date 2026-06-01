"""메모리 사용률 수집기."""

import psutil


def read_mem_usage() -> float:
    """현재 메모리 사용률(%)을 반환한다."""
    return psutil.virtual_memory().percent
