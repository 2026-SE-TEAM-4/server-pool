from app import config
from app import load_injector as li


def test_cpu_cmd_contains_sentinel_and_load():
    cmd = li.build_cpu_cmd(50)
    joined = " ".join(cmd)
    assert config.CPU_LOAD_SENTINEL in joined
    assert "0.5" in joined  # 50% → load fraction 0.5
    assert cmd[0] == "python"


def test_ram_cmd_scales_mb_by_percent():
    cmd = li.build_ram_cmd(50)
    joined = " ".join(cmd)
    assert config.RAM_LOAD_SENTINEL in joined
    # 50% → RAM_LOAD_MB_PER_100의 절반 MB
    assert str(config.RAM_LOAD_MB_PER_100 // 2) in joined


def test_pkill_cmd_targets_sentinel():
    assert li.build_pkill_cmd(config.CPU_LOAD_SENTINEL) == [
        "pkill", "-f", config.CPU_LOAD_SENTINEL,
    ]


def test_gpu_set_cmd_writes_override_file():
    cmd = li.build_gpu_set_cmd(80)
    assert cmd[0] == "sh"
    joined = " ".join(cmd)
    assert config.GPU_OVERRIDE_PATH in joined
    assert "80" in joined


def test_gpu_clear_cmd_removes_file():
    assert li.build_gpu_clear_cmd() == ["rm", "-f", config.GPU_OVERRIDE_PATH]
