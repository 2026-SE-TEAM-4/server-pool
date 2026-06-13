"""에이전트 HTTP 클라이언트. /metrics를 읽고 미응답이면 명시적으로 offline 표현.

예외를 삼키지 않고 AgentMetrics(online=False)로 변환해 호출 측이 OFFLINE을
표시하게 한다. client 인자는 테스트 주입용(MockTransport).
"""

from dataclasses import dataclass

import httpx

from app import config


@dataclass
class AgentMetrics:
    online: bool
    cpu: float | None = None
    mem: float | None = None
    gpu: float | None = None
    net: float | None = None


def fetch_metrics(
    host: str, port: int, *, client: httpx.Client | None = None, timeout: float = 2.0
) -> AgentMetrics:
    own = client is None
    client = client or httpx.Client(timeout=timeout)
    try:
        resp = client.get(f"http://{host}:{port}/metrics")
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        return AgentMetrics(online=False)
    finally:
        if own:
            client.close()
    return AgentMetrics(
        online=True,
        cpu=data.get("cpuUsage"),
        mem=data.get("memUsage"),
        gpu=data.get("gpuUsage"),
        net=data.get("netUsage"),
    )


def fetch_for(server_id: int, **kwargs) -> AgentMetrics:
    return fetch_metrics(config.AGENT_HOST, config.agent_port(server_id), **kwargs)
