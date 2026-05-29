"""서버 풀 에이전트 진입점.

백엔드가 수집해 갈 대상 서버 한 대를 흉내낸다. 현재 /metrics는 자리값이며,
실제 수집 로직과 메트릭 JSON 계약은 단일 출처(설계 문서) 확정 후 구현한다.
계약을 본 레포에서 임의로 확정하지 않는다(rule.md / CLAUDE.md).
"""

from fastapi import FastAPI

from agent.config import SERVER_ID

app = FastAPI(title=f"server-pool agent #{SERVER_ID}")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
async def metrics() -> dict:
    # 자리값. 실제 수집·필드 계약은 후속 단계(설계 문서가 단일 출처).
    return {
        "serverId": SERVER_ID,
        "cpuUsage": 0.0,
        "memUsage": 0.0,
        "netUsage": 0.0,
        "status": "AVAILABLE",
    }
