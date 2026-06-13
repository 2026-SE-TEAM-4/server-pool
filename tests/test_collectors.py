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


import agent.collectors.cpu as cpu_mod
import agent.collectors.gpu as gpu_mod
import agent.collectors.memory as mem_mod


def test_gpu_override_returns_file_value(tmp_path, monkeypatch) -> None:
    override = tmp_path / "gpu_override"
    override.write_text("73.5")
    monkeypatch.setattr(gpu_mod, "GPU_OVERRIDE_PATH", str(override))
    monkeypatch.setattr(gpu_mod, "GPU_SIMULATE", True)
    assert gpu_mod.read_gpu_usage() == 73.5


def test_gpu_override_ignored_when_out_of_range(tmp_path, monkeypatch) -> None:
    override = tmp_path / "gpu_override"
    override.write_text("250")
    monkeypatch.setattr(gpu_mod, "GPU_OVERRIDE_PATH", str(override))
    monkeypatch.setattr(gpu_mod, "GPU_SIMULATE", True)
    value = gpu_mod.read_gpu_usage()
    assert 0.0 <= value <= 100.0  # 범위 밖 오버라이드는 무시, 합성값 사용


def test_gpu_override_ignored_when_not_simulated(tmp_path, monkeypatch) -> None:
    override = tmp_path / "gpu_override"
    override.write_text("50")
    monkeypatch.setattr(gpu_mod, "GPU_OVERRIDE_PATH", str(override))
    monkeypatch.setattr(gpu_mod, "GPU_SIMULATE", False)
    assert gpu_mod.read_gpu_usage() is None  # GPU 미탑재 서버는 항상 None


def test_cpu_override_returns_file_value(tmp_path, monkeypatch) -> None:
    override = tmp_path / "cpu_override"
    override.write_text("55.0")
    monkeypatch.setattr(cpu_mod, "CPU_OVERRIDE_PATH", str(override))
    assert cpu_mod.read_cpu_usage() == 55.0


def test_cpu_override_ignored_when_out_of_range(tmp_path, monkeypatch) -> None:
    override = tmp_path / "cpu_override"
    override.write_text("250")
    monkeypatch.setattr(cpu_mod, "CPU_OVERRIDE_PATH", str(override))
    value = cpu_mod.read_cpu_usage()
    assert 0.0 <= value <= 100.0


def test_mem_override_returns_file_value(tmp_path, monkeypatch) -> None:
    override = tmp_path / "mem_override"
    override.write_text("42.0")
    monkeypatch.setattr(mem_mod, "MEM_OVERRIDE_PATH", str(override))
    assert mem_mod.read_mem_usage() == 42.0


def test_mem_override_ignored_when_out_of_range(tmp_path, monkeypatch) -> None:
    override = tmp_path / "mem_override"
    override.write_text("-10")
    monkeypatch.setattr(mem_mod, "MEM_OVERRIDE_PATH", str(override))
    value = mem_mod.read_mem_usage()
    assert 0.0 <= value <= 100.0


from agent import sim as sim_mod


def test_cpu_override_wins_in_every_mode(tmp_path, monkeypatch):
    override = tmp_path / "cpu_ov"
    override.write_text("88.0")
    mode_file = tmp_path / "mode"
    monkeypatch.setattr(cpu_mod, "CPU_OVERRIDE_PATH", str(override))
    monkeypatch.setattr(sim_mod, "MODE_PATH", str(mode_file))
    for mode in ("stable", "real", "randomwalk"):
        mode_file.write_text(mode)
        assert cpu_mod.read_cpu_usage() == 88.0


def test_cpu_stable_uses_baseline_and_stays_in_range(tmp_path, monkeypatch):
    baseline = tmp_path / "cpu_base"
    baseline.write_text("80")
    monkeypatch.setattr(cpu_mod, "CPU_BASELINE_PATH", str(baseline))
    monkeypatch.setattr(cpu_mod, "CPU_OVERRIDE_PATH", str(tmp_path / "absent"))
    monkeypatch.setattr(sim_mod, "MODE_PATH", str(tmp_path / "absent"))
    monkeypatch.setattr(sim_mod, "DEFAULT_MODE", "stable")
    values = [cpu_mod.read_cpu_usage() for _ in range(150)]
    assert all(5.0 <= v <= 95.0 for v in values)
    assert 60.0 <= (sum(values) / len(values)) <= 95.0


def test_mem_override_wins(tmp_path, monkeypatch):
    override = tmp_path / "mem_ov"
    override.write_text("55.0")
    monkeypatch.setattr(mem_mod, "MEM_OVERRIDE_PATH", str(override))
    monkeypatch.setattr(sim_mod, "MODE_PATH", str(tmp_path / "absent"))
    assert mem_mod.read_mem_usage() == 55.0


def test_mem_stable_in_range(tmp_path, monkeypatch):
    monkeypatch.setattr(mem_mod, "MEM_OVERRIDE_PATH", str(tmp_path / "absent"))
    monkeypatch.setattr(mem_mod, "MEM_BASELINE_PATH", str(tmp_path / "absent"))
    monkeypatch.setattr(sim_mod, "MODE_PATH", str(tmp_path / "absent"))
    monkeypatch.setattr(sim_mod, "DEFAULT_MODE", "stable")
    values = [mem_mod.read_mem_usage() for _ in range(120)]
    assert all(10.0 <= v <= 90.0 for v in values)


def test_gpu_real_mode_returns_none(tmp_path, monkeypatch):
    mode_file = tmp_path / "mode"
    mode_file.write_text("real")
    monkeypatch.setattr(sim_mod, "MODE_PATH", str(mode_file))
    monkeypatch.setattr(gpu_mod, "GPU_SIMULATE", True)
    monkeypatch.setattr(gpu_mod, "GPU_OVERRIDE_PATH", str(tmp_path / "absent"))
    assert gpu_mod.read_gpu_usage() is None


def test_gpu_disabled_always_none(tmp_path, monkeypatch):
    monkeypatch.setattr(gpu_mod, "GPU_SIMULATE", False)
    monkeypatch.setattr(sim_mod, "MODE_PATH", str(tmp_path / "absent"))
    assert gpu_mod.read_gpu_usage() is None


def test_gpu_stable_in_range(tmp_path, monkeypatch):
    monkeypatch.setattr(gpu_mod, "GPU_SIMULATE", True)
    monkeypatch.setattr(gpu_mod, "GPU_OVERRIDE_PATH", str(tmp_path / "absent"))
    monkeypatch.setattr(gpu_mod, "GPU_BASELINE_PATH", str(tmp_path / "absent"))
    monkeypatch.setattr(sim_mod, "MODE_PATH", str(tmp_path / "absent"))
    monkeypatch.setattr(sim_mod, "DEFAULT_MODE", "stable")
    values = [gpu_mod.read_gpu_usage() for _ in range(120)]
    assert all(v is not None and 0.0 <= v <= 100.0 for v in values)
