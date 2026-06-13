import pytest

from app import config, sim_control


def test_build_set_mode_cmd_valid():
    cmd = sim_control.build_set_mode_cmd("real")
    assert cmd == ["sh", "-c", f"echo real > {config.MODE_PATH}"]


def test_build_set_mode_cmd_rejects_unknown():
    with pytest.raises(ValueError):
        sim_control.build_set_mode_cmd("bogus")


def test_build_set_baseline_cmd_clamps():
    cmd = sim_control.build_set_baseline_cmd(config.CPU_BASELINE_PATH, 150)
    assert cmd == ["sh", "-c", f"echo 100 > {config.CPU_BASELINE_PATH}"]


def test_build_clear_cmd():
    assert sim_control.build_clear_cmd(config.MODE_PATH) == ["rm", "-f", config.MODE_PATH]
