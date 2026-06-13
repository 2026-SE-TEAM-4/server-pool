from app import config


def test_agent_port_is_base_plus_id():
    assert config.agent_port(1) == 9101
    assert config.agent_port(6) == 9106


def test_service_name():
    assert config.service_name(3) == "agent-3"


def test_service_to_server_id():
    assert config.service_to_server_id("agent-3") == 3
    assert config.service_to_server_id("agent-12") == 12
    assert config.service_to_server_id("postgres") is None
    assert config.service_to_server_id("agent-x") is None


def test_server_ids_default():
    assert config.SERVER_IDS == [1, 2, 3, 4, 5, 6]
