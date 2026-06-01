"""네트워크 사용률 수집기.

사용률은 NIC 대역폭(NET_CAP_MBPS) 대비 백분율로 정의한다. psutil은 누적
송수신 바이트만 주므로, 직전 호출과의 증가분과 경과 시간으로 순간 처리량을
계산해 대역폭으로 나눈다. 모듈 수준에 직전 표본을 둔다(상태가 있어야 증가분을
구할 수 있기 때문).
"""

import time

import psutil

from agent.config import NET_CAP_MBPS

# (monotonic 시각, 누적 송수신 바이트). 첫 호출 전에는 None.
_last_sample: tuple[float, int] | None = None


def read_net_usage() -> float:
    """NIC 대역폭 대비 네트워크 사용률(%)을 반환한다.

    첫 호출은 기준점만 잡고 0.0을 반환한다.
    """
    global _last_sample
    counters = psutil.net_io_counters()
    total_bytes = counters.bytes_sent + counters.bytes_recv
    now = time.monotonic()

    if _last_sample is None:
        _last_sample = (now, total_bytes)
        return 0.0

    last_time, last_bytes = _last_sample
    _last_sample = (now, total_bytes)

    elapsed = now - last_time
    if elapsed <= 0:
        return 0.0

    mbps = (total_bytes - last_bytes) * 8 / 1_000_000 / elapsed
    return round(min(100.0, mbps / NET_CAP_MBPS * 100), 1)
