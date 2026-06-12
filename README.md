# server-pool

서버 예약/할당 관리 시스템의 **서버 풀 에이전트**.
백엔드(APScheduler)가 메트릭을 수집할 대상 서버들을 동일한 경량 에이전트 이미지
N개로 시뮬레이션한다. 각 컨테이너는 `:91xx`의 `/metrics`·`/health`를 노출한다.

> **현재 상태.** 부팅·`/health`·`/metrics`까지 동작한다. `/metrics`는 psutil로
> CPU·메모리·네트워크를 측정하며, 모든 컨테이너가 같은 호스트를 공유해 값이 서로
> 거의 같으므로 CPU·메모리는 서버별 합성 편차를 더해 대시보드에서 구분되게 한다
> (네트워크는 컨테이너별 NIC라 편차 없이 실측). GPU는 시뮬레이션 환경에 물리 GPU가
> 없어 합성값(`GPU_SIMULATE`)을 낸다. 프론트엔드가 브라우저에서 직접 읽을 수 있도록
> CORS(공개 읽기 전용)를 연다. 필드·단위 계약의 단일 출처는
> `diagram-and-docs/serverpool-spec.html`(서버 풀 명세서)이다.

## 구성

- 기본 5대: `agent-1`~`agent-5`, 호스트 포트 9101~9105.
- 각 인스턴스는 `SERVER_ID`·`PORT`를 compose에서 주입받는다.
- 백엔드 컨테이너는 `host.docker.internal:9101..9105`으로 수집한다.

## 실행

```bash
docker compose up --build -d
curl localhost:9101/health     # {"status":"ok"}
curl localhost:9101/metrics    # 사용률 JSON (serverId, collectedAt, cpu/mem/gpu/netUsage, status)
```

## 제어 CLI

서버 상태 확인, 강제 종료, 부하 주입을 대화형 메뉴로 조작한다.

```bash
uv run python scripts/ctl.py
```

실행하면 arrow key로 탐색하는 메뉴가 열린다.

```
서버풀 제어 CLI

 ID │ Port │ 상태 │  CPU   │  MEM   │  GPU   │  NET
────┼──────┼──────┼────────┼────────┼────────┼──────
  1 │ 9101 │  UP  │  12.3% │  65.0% │  34.2% │  0.0%
  2 │ 9102 │  UP  │  11.0% │  67.1% │  81.8% │  0.0%
  ...

메뉴를 선택하세요
❯ 상태 새로고침
  서버 제어  (기동 / 재시작 / 강제종료)
  부하 주입  (CPU / MEM / GPU / NET 오버라이드)
  오버라이드 해제
  종료
```

| 메뉴 | 동작 |
|------|------|
| 상태 새로고침 | 현재 메트릭 테이블 다시 출력 |
| 서버 제어 | 기동 / 재시작 / 강제 종료(SIGKILL) — 서버 단위 선택 |
| 부하 주입 | 프리셋(full / cpu-spike / mem-spike 등) 또는 커스텀 수치로 메트릭 오버라이드 |
| 오버라이드 해제 | 주입된 값 제거, 실측값 복귀 |

- 부하 주입은 실제 호스트에 부하를 걸지 않고 `/inject` 엔드포인트로 수치만 바꾼다.
- `Ctrl+C` 또는 종료 메뉴로 빠져나온다.
- `questionary`·`rich` 가 필요하다(`uv sync --dev` 로 설치됨).

## 환경 변수

| 키 | 기본 | 설명 |
| --- | --- | --- |
| PORT | 9101 | 에이전트 listen 포트 |
| SERVER_ID | 1 | 에이전트 식별(인스턴스별 주입) |
| NET_CAP_MBPS | 1000 | 네트워크 사용률 계산 기준 대역폭(Mbps) |
| GPU_SIMULATE | true | 물리 GPU가 없을 때 합성 GPU 사용률 노출 여부 |

## /metrics 응답 (계약 요약)

```json
{ "serverId": 1, "collectedAt": "2026-06-01T09:00:00Z",
  "cpuUsage": 37.5, "memUsage": 61.2, "gpuUsage": 88.0, "netUsage": 12.4, "status": "OK" }
```

사용률은 float 0–100(%), `gpuUsage`는 `GPU_SIMULATE=false`거나 GPU 미탑재면 `null`.
`status`는 에이전트가 응답하는 한 항상 `OK`(MISSING/NA는 백엔드가 판정). 전체 계약은
서버 풀 명세서를 따른다.

## 테스트

```bash
uv run pytest          # 수집기 범위·타입 검증 (tests/test_collectors.py)
```

## 장애·부하 시연

CLI(`scripts/ctl.py`)에서 대화형으로 조작하는 것을 권장한다.
직접 HTTP로 제어할 경우 아래 엔드포인트를 사용한다.

```bash
# 메트릭 오버라이드 주입 (실제 부하 없이 수치만 변경)
curl -X POST localhost:9101/inject \
     -H "Content-Type: application/json" \
     -d '{"cpu": 100, "mem": 85, "gpu": 90, "net": 70}'

# 오버라이드 해제, 실측 복귀
curl -X POST localhost:9101/reset

# 서버 강제 종료 후 복구
docker kill server-pool-agent-3-1
docker compose up -d agent-3
```

## 후속(미구현)

- 실제 GPU 노드 연동(현재는 `GPU_SIMULATE` 합성값)
- 재현용 `scripts/scenarios/`

## 관련 레포

- `backend` — 본 에이전트로부터 메트릭을 수집하는 FastAPI/APScheduler
- `diagram-and-docs` — 전체 시스템 설계 문서(서버 풀 명세서 포함)
