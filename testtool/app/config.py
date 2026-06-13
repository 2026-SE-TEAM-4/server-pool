"""테스트 툴 상수와 매핑.

server-pool/docker-compose.yml 규약: 서비스명 agent-N, 퍼블리시 포트 9100+N.
에이전트는 호스트에서 127.0.0.1:<port>로 도달한다.
"""

# 도커 compose 서비스명 → SERVER_ID 발견에 쓰는 라벨 키.
COMPOSE_SERVICE_LABEL = "com.docker.compose.service"

SERVER_IDS = [1, 2, 3, 4, 5, 6]
AGENT_HOST = "127.0.0.1"
BASE_PORT = 9100  # 포트 = BASE_PORT + SERVER_ID

# 에이전트가 읽는 오버라이드 파일(agent/collectors/*.py와 동일 경로).
GPU_OVERRIDE_PATH = "/tmp/agent_gpu_override"
CPU_OVERRIDE_PATH = "/tmp/agent_cpu_override"
MEM_OVERRIDE_PATH = "/tmp/agent_mem_override"

# 폴링 주기(ms).
POLL_INTERVAL_MS = 2500


def agent_port(server_id: int) -> int:
    return BASE_PORT + server_id


def service_name(server_id: int) -> str:
    return f"agent-{server_id}"


def service_to_server_id(service: str) -> int | None:
    """compose 서비스명 'agent-N' → N. 매칭 안 되면 None."""
    if not service.startswith("agent-"):
        return None
    suffix = service.split("-", 1)[1]
    if not suffix.isdigit():
        return None
    return int(suffix)
