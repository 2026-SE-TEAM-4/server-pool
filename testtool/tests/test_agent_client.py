import httpx

from app import agent_client as ac


def _client_returning(payload, status=200):
    def handler(request):
        return httpx.Response(status, json=payload)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_metrics_parses_payload():
    payload = {"cpuUsage": 42.0, "memUsage": 61.2, "gpuUsage": 88.0, "netUsage": 12.4}
    metrics = ac.fetch_metrics("h", 9101, client=_client_returning(payload))
    assert metrics.online is True
    assert metrics.cpu == 42.0
    assert metrics.gpu == 88.0


def test_fetch_metrics_offline_on_error():
    def handler(request):
        raise httpx.ConnectError("down")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    metrics = ac.fetch_metrics("h", 9101, client=client)
    assert metrics.online is False
    assert metrics.cpu is None


def test_fetch_metrics_offline_on_5xx():
    metrics = ac.fetch_metrics("h", 9101, client=_client_returning({}, status=503))
    assert metrics.online is False
