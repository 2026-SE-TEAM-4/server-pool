"""서버 풀 에이전트 진입점.

백엔드(SYS 수집기)가 1분 주기로 PULL해 갈 대상 서버 한 대를 흉내낸다.
/metrics는 collectors가 측정한 현재 사용률 스냅샷을 반환하며, 필드·단위 계약의
단일 출처는 diagram-and-docs/serverpool-spec.html(서버 풀 명세서)이다.
"""

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent.collectors.cpu import read_cpu_usage
from agent.collectors.gpu import read_gpu_usage
from agent.collectors.memory import read_mem_usage
from agent.collectors.net import read_net_usage
from agent.config import SERVER_ID

app = FastAPI(title=f"server-pool agent #{SERVER_ID}")

# 프론트엔드(React SPA)가 브라우저에서 /metrics를 직접 읽을 수 있게 CORS를 연다.
# 공개 읽기 전용 엔드포인트라 인증 쿠키가 없으므로 allow_credentials는 켜지 않는다.
# (와일드카드 origin과 credentials를 함께 켜면 브라우저가 응답을 거부한다.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
def metrics() -> dict:
    """현재 자원 사용률 스냅샷(서버풀 /metrics 계약).

    psutil 기반 측정은 동기 호출이라 sync 엔드포인트로 두어 FastAPI가 스레드풀에서
    처리하게 한다(이벤트 루프 차단 방지). status는 에이전트가 응답하는 한 항상 OK이며,
    MISSING/NA 판정은 백엔드 수집기 몫이다.
    """
    return {
        "serverId": SERVER_ID,
        "collectedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cpuUsage": read_cpu_usage(),
        "memUsage": read_mem_usage(),
        "gpuUsage": read_gpu_usage(),
        "netUsage": read_net_usage(),
        "status": "OK",
    }
