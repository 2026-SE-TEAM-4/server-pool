from unittest.mock import MagicMock

from app import config
from app.docker_control import DockerControl


def _fake_container(service: str, status: str = "running"):
    c = MagicMock()
    c.labels = {config.COMPOSE_SERVICE_LABEL: service}
    c.status = status
    return c


def _control_with(containers):
    client = MagicMock()
    client.containers.list.return_value = containers
    return DockerControl(client=client), client


def test_discover_maps_service_to_server_id():
    ctrl, _ = _control_with([_fake_container("agent-1"), _fake_container("agent-3")])
    found = ctrl.discover()
    assert set(found.keys()) == {1, 3}


def test_status_returns_offline_when_missing():
    ctrl, _ = _control_with([_fake_container("agent-1")])
    ctrl.discover()
    assert ctrl.status(1) == "running"
    assert ctrl.status(2) == "offline"


def test_stop_calls_container_stop():
    container = _fake_container("agent-1")
    ctrl, _ = _control_with([container])
    ctrl.discover()
    ctrl.stop(1)
    container.stop.assert_called_once()


def test_restart_calls_container_restart():
    container = _fake_container("agent-1")
    ctrl, _ = _control_with([container])
    ctrl.discover()
    ctrl.restart(1)
    container.restart.assert_called_once()


def test_exec_run_invokes_exec(monkeypatch):
    container = _fake_container("agent-1")
    ctrl, _ = _control_with([container])
    ctrl.discover()
    ctrl.exec_run(1, ["pkill", "-f", "x"])
    container.exec_run.assert_called_once_with(["pkill", "-f", "x"])


def test_exec_detached_invokes_exec_with_detach():
    container = _fake_container("agent-1")
    ctrl, _ = _control_with([container])
    ctrl.discover()
    ctrl.exec_detached(1, ["python", "-c", "x"])
    _, kwargs = container.exec_run.call_args
    assert kwargs.get("detach") is True
