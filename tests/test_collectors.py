"""수집기 단위 테스트.

값이 /metrics 계약 범위(사용률 0~100, gpu는 float 또는 None)를 지키는지 본다.
실제 수치는 환경마다 다르므로 범위·타입만 검증한다.
"""

from agent.collectors.cpu import read_cpu_usage
from agent.collectors.gpu import read_gpu_usage
from agent.collectors.memory import read_mem_usage
from agent.collectors.net import read_net_usage


def test_cpu_usage_in_range() -> None:
    value = read_cpu_usage()
    assert isinstance(value, float)
    assert 0.0 <= value <= 100.0


def test_mem_usage_in_range() -> None:
    value = read_mem_usage()
    assert isinstance(value, float)
    assert 0.0 <= value <= 100.0


def test_net_usage_in_range() -> None:
    read_net_usage()  # 첫 호출은 기준점만 잡는다.
    value = read_net_usage()
    assert isinstance(value, float)
    assert 0.0 <= value <= 100.0


def test_gpu_usage_in_range_or_none() -> None:
    value = read_gpu_usage()
    assert value is None or (0.0 <= value <= 100.0)
