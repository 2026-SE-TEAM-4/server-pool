from unittest.mock import MagicMock

from app import config
from app import load_injector as li


def test_set_cmd_writes_value_to_path():
    cmd = li.build_set_cmd(config.CPU_OVERRIDE_PATH, 50)
    assert cmd[0] == "sh"
    joined = " ".join(cmd)
    assert config.CPU_OVERRIDE_PATH in joined
    assert "50" in joined


def test_set_cmd_clamps_percent():
    assert "100" in " ".join(li.build_set_cmd(config.GPU_OVERRIDE_PATH, 250))
    assert "0" in " ".join(li.build_set_cmd(config.GPU_OVERRIDE_PATH, -5))


def test_clear_cmd_removes_path():
    assert li.build_clear_cmd(config.MEM_OVERRIDE_PATH) == ["rm", "-f", config.MEM_OVERRIDE_PATH]


def test_apply_methods_target_correct_override_paths():
    docker = MagicMock()
    inj = li.LoadInjector(docker)
    inj.apply_cpu(1, 50)
    inj.apply_ram(1, 60)
    inj.set_gpu(1, 70)
    cmds = [call.args[1] for call in docker.exec_run.call_args_list]
    joined = [" ".join(c) for c in cmds]
    assert any(config.CPU_OVERRIDE_PATH in j for j in joined)
    assert any(config.MEM_OVERRIDE_PATH in j for j in joined)
    assert any(config.GPU_OVERRIDE_PATH in j for j in joined)


def test_revert_all_clears_three_paths():
    docker = MagicMock()
    inj = li.LoadInjector(docker)
    inj.revert_all(1)
    cmds = [" ".join(call.args[1]) for call in docker.exec_run.call_args_list]
    assert any(config.CPU_OVERRIDE_PATH in c and "rm" in c for c in cmds)
    assert any(config.MEM_OVERRIDE_PATH in c and "rm" in c for c in cmds)
    assert any(config.GPU_OVERRIDE_PATH in c and "rm" in c for c in cmds)
