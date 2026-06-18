"""서버 풀 에이전트 진입점.

백엔드(SYS 수집기)가 1분 주기로 PULL해 갈 대상 서버 한 대를 흉내낸다.
/metrics는 collectors가 측정한 현재 사용률 스냅샷을 반환하며, 필드·단위 계약의
단일 출처는 diagram-and-docs/serverpool-spec.html(서버 풀 명세서)이다.
/info는 정적 하드웨어 사양을 반환한다(config.py의 SERVER_SPECS에서 읽음).
/control은 데모·테스트에서 curl로 이상값/장애를 주입한다(docker exec 없이).
"""

import asyncio
import os
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from agent import sim
from agent.collectors import cpu, gpu, memory, net
from agent.collectors.cpu import read_cpu_usage
from agent.collectors.gpu import read_gpu_usage
from agent.collectors.memory import read_mem_usage
from agent.collectors.net import read_net_usage
from agent.config import SERVER_ID, SPEC

app = FastAPI(title=f"server-pool agent #{SERVER_ID}")

# 자원 이름 -> 해당 수집기의 override 파일 경로.
# 수집기가 읽는 모듈 변수를 단일 출처로 삼아, /control은 같은 파일에만 쓴다.
_OVERRIDE_PATHS = {
    "cpu": cpu.CPU_OVERRIDE_PATH,
    "mem": memory.MEM_OVERRIDE_PATH,
    "gpu": gpu.GPU_OVERRIDE_PATH,
    "net": net.NET_OVERRIDE_PATH,
}

# unhealthy 플래그는 프로세스 메모리에만 둔다(파일 불필요). /control로 켜고 끈다.
_unhealthy = False
# ttl 자동 복구 타이머. 새 요청이 오면 이전 타이머를 취소한다.
_revert_task: asyncio.Task | None = None


class ControlRequest(BaseModel):
    """/control 주입 요청. 모든 필드는 선택이며, 준 필드만 적용한다."""

    cpu: float | None = Field(default=None, ge=0, le=100)
    mem: float | None = Field(default=None, ge=0, le=100)
    gpu: float | None = Field(default=None, ge=0, le=100)
    net: float | None = Field(default=None, ge=0, le=100)
    mode: str | None = None
    unhealthy: bool | None = None
    ttl_seconds: int | None = Field(default=None, gt=0)
    reset: bool = False


def _clear_overrides() -> None:
    """주입한 override·모드 파일을 지우고 unhealthy를 푼다(주입 전 상태로 복구)."""
    global _unhealthy
    for path in (*_OVERRIDE_PATHS.values(), sim.MODE_PATH):
        try:
            os.remove(path)
        except OSError:
            pass
    _unhealthy = False


def _apply(req: ControlRequest) -> None:
    """요청에 담긴 값만 override·모드 파일에 쓰고 unhealthy를 갱신한다."""
    global _unhealthy
    for name, value in (("cpu", req.cpu), ("mem", req.mem), ("gpu", req.gpu), ("net", req.net)):
        if value is not None:
            with open(_OVERRIDE_PATHS[name], "w") as f:
                f.write(str(value))
    if req.mode is not None:
        with open(sim.MODE_PATH, "w") as f:
            f.write(req.mode)
    if req.unhealthy is not None:
        _unhealthy = req.unhealthy


async def _revert_after(ttl_seconds: int) -> None:
    """ttl 경과 후 주입을 자동 해제한다(반복 시연을 위해 스파이크가 스스로 되돌아옴)."""
    try:
        await asyncio.sleep(ttl_seconds)
    except asyncio.CancelledError:
        return
    _clear_overrides()


def _cancel_revert() -> None:
    global _revert_task
    if _revert_task is not None and not _revert_task.done():
        _revert_task.cancel()
    _revert_task = None


@app.get("/health")
async def health():
    """unhealthy 플래그가 켜져 있으면 503으로 응답한다.

    컨테이너를 죽이지 않고 '응답은 하지만 비정상'을 시연하기 위함이다
    (이상탐지·인시던트 상관분석 데모용).
    """
    if _unhealthy:
        return JSONResponse(status_code=503, content={"status": "unhealthy"})
    return {"status": "ok"}


@app.get("/info")
async def info() -> dict:
    """정적 하드웨어 사양을 반환한다.

    백엔드 시드 스크립트나 관리 툴에서 서버 정보를 조회할 때 사용한다.
    값은 config.SERVER_SPECS에 정의된 상수이며 런타임에 변하지 않는다.
    """
    return {"serverId": SERVER_ID, **SPEC}


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


@app.post("/control")
async def control(req: ControlRequest) -> dict:
    """런타임 이상값/장애 주입. 기존 override 파일 메커니즘을 재사용한다.

    준 필드만 적용한다. reset이 true면 모든 주입을 해제한다. ttl_seconds를 주면
    그 시간 뒤 자동 복구된다(이전 ttl 타이머는 새 요청마다 취소·재설정).
    """
    global _revert_task
    _cancel_revert()
    if req.reset:
        _clear_overrides()
        return {"status": "reset"}
    _apply(req)
    if req.ttl_seconds is not None:
        _revert_task = asyncio.create_task(_revert_after(req.ttl_seconds))
    return {"status": "applied", "ttlSeconds": req.ttl_seconds}


@app.delete("/control")
async def control_reset() -> dict:
    """주입 해제. POST /control {reset:true}와 동일하다."""
    _cancel_revert()
    _clear_overrides()
    return {"status": "reset"}
