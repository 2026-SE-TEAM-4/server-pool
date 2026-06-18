"""엔드포인트 계약 테스트.

FastAPI TestClient로 /health·/metrics·/control을 docker 없이 검증한다.
/metrics는 서버풀 JSON 계약(camelCase 키·타입)을 지켜야 한다.
/control 라운드트립은 override 파일 메커니즘을 그대로 쓰므로, 실제 /tmp를
건드리지 않도록 경로를 tmp_path로 monkeypatch한다(다른 테스트와 격리).
"""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

import agent.collectors.cpu as cpu_mod
import agent.collectors.gpu as gpu_mod
import agent.collectors.memory as mem_mod
import agent.collectors.net as net_mod
import agent.main as main
from agent import sim as sim_mod

client = TestClient(main.app)


def test_health_ok() -> None:
    main._unhealthy = False
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_metrics_contract_keys_and_types() -> None:
    body = client.get("/metrics").json()
    assert isinstance(body["serverId"], int)
    assert isinstance(body["cpuUsage"], float)
    assert isinstance(body["memUsage"], float)
    assert isinstance(body["netUsage"], float)
    assert body["status"] == "OK"
    # gpuUsage는 합성 모드면 float, real 모드/미탑재면 None (계약상 허용).
    assert body["gpuUsage"] is None or isinstance(body["gpuUsage"], float)
    # collectedAt은 ISO 8601(Z)로 파싱 가능해야 한다.
    parsed = datetime.fromisoformat(body["collectedAt"].replace("Z", "+00:00"))
    assert parsed.tzinfo is not None


def test_metrics_gpu_null_in_real_mode(tmp_path, monkeypatch) -> None:
    mode_file = tmp_path / "mode"
    mode_file.write_text("real")
    monkeypatch.setattr(sim_mod, "MODE_PATH", str(mode_file))
    monkeypatch.setattr(gpu_mod, "GPU_SIMULATE", True)
    monkeypatch.setattr(gpu_mod, "GPU_OVERRIDE_PATH", str(tmp_path / "absent"))
    assert client.get("/metrics").json()["gpuUsage"] is None


def test_metrics_gpu_present_in_synthetic_mode(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(sim_mod, "MODE_PATH", str(tmp_path / "absent"))
    monkeypatch.setattr(sim_mod, "DEFAULT_MODE", "stable")
    monkeypatch.setattr(gpu_mod, "GPU_SIMULATE", True)
    monkeypatch.setattr(gpu_mod, "GPU_OVERRIDE_PATH", str(tmp_path / "absent"))
    monkeypatch.setattr(gpu_mod, "GPU_BASELINE_PATH", str(tmp_path / "absent"))
    assert isinstance(client.get("/metrics").json()["gpuUsage"], float)


@pytest.fixture
def isolated_paths(tmp_path, monkeypatch):
    """override·모드 파일 경로를 tmp_path로 돌려 실제 /tmp 오염을 막는다."""
    paths = {
        "cpu": str(tmp_path / "cpu_override"),
        "mem": str(tmp_path / "mem_override"),
        "gpu": str(tmp_path / "gpu_override"),
        "net": str(tmp_path / "net_override"),
    }
    monkeypatch.setattr(cpu_mod, "CPU_OVERRIDE_PATH", paths["cpu"])
    monkeypatch.setattr(mem_mod, "MEM_OVERRIDE_PATH", paths["mem"])
    monkeypatch.setattr(gpu_mod, "GPU_OVERRIDE_PATH", paths["gpu"])
    monkeypatch.setattr(net_mod, "NET_OVERRIDE_PATH", paths["net"])
    monkeypatch.setattr(gpu_mod, "GPU_SIMULATE", True)
    monkeypatch.setattr(sim_mod, "MODE_PATH", str(tmp_path / "mode"))
    monkeypatch.setattr(main, "_OVERRIDE_PATHS", paths)
    main._unhealthy = False
    return paths


def test_control_override_reflected_in_metrics(isolated_paths) -> None:
    client.post("/control", json={"cpu": 95, "gpu": 88})
    body = client.get("/metrics").json()
    assert body["cpuUsage"] == 95.0
    assert body["gpuUsage"] == 88.0


def test_control_unhealthy_flips_health(isolated_paths) -> None:
    client.post("/control", json={"unhealthy": True})
    assert client.get("/health").status_code == 503

    client.delete("/control")
    assert client.get("/health").status_code == 200


def test_control_reset_clears_override(isolated_paths) -> None:
    client.post("/control", json={"cpu": 70})
    assert client.get("/metrics").json()["cpuUsage"] == 70.0

    client.post("/control", json={"reset": True})
    # override 파일이 지워지면 합성값으로 돌아가 70 고정값이 아니다(여러 번 확인).
    values = {client.get("/metrics").json()["cpuUsage"] for _ in range(5)}
    assert values != {70.0}
