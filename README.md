# server-pool

서버 예약/할당 관리 시스템의 **서버 풀 에이전트**.
백엔드(APScheduler)가 메트릭을 수집할 대상 서버들을 동일한 경량 에이전트 이미지
N개로 시뮬레이션한다. 각 컨테이너는 `:91xx`의 `/metrics`·`/health`를 노출한다.

> **현재 상태.** 부팅·`/health`·`/metrics`(실측)까지 동작한다. `/metrics`는 psutil로
> CPU·메모리·네트워크를 실측하고, GPU는 시뮬레이션 환경에 물리 GPU가 없어 합성값
> (`GPU_SIMULATE`)을 낸다. 필드·단위 계약의 단일 출처는
> `diagram-and-docs/serverpool-spec.html`(서버 풀 명세서)이다.

## 구성

- 기본 3대: `agent-1`·`agent-2`·`agent-3`, 호스트 포트 9101·9102·9103.
- 각 인스턴스는 `SERVER_ID`·`PORT`를 compose에서 주입받는다.
- 백엔드 컨테이너는 `host.docker.internal:9101..9103`으로 수집한다.

## 실행

```bash
docker compose up --build -d
curl localhost:9101/health     # {"status":"ok"}
curl localhost:9101/metrics    # 사용률 JSON (serverId, collectedAt, cpu/mem/gpu/netUsage, status)
```

대수를 늘리려면 compose에 `agent-4` … 를 같은 형식(고정 포트 publish)으로 추가한다.

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

## 장애·부하 시연 (이미지에 stress-ng·hey 포함)

에이전트에는 별도 컨트롤 엔드포인트를 두지 않는다. 모든 시나리오는 외부 docker 명령으로 일으킨다.
부하를 주면 `/metrics`의 cpu/mem/net 실측값이 반응한다.

```bash
docker compose exec agent-3 stress-ng --cpu 4 --timeout 60s              # CPU 부하
docker compose exec agent-3 stress-ng --vm 2 --vm-bytes 1G --timeout 60s # 메모리
docker pause agent-3   # 메트릭 송신 중단 (docker unpause 로 복구)
docker stop agent-3    # 서버 다운 (docker start 로 복구)
hey -z 30s -c 100 http://localhost:9101/metrics                          # 트래픽 폭증
```

## 후속(미구현)

- 실제 GPU 노드 연동(현재는 `GPU_SIMULATE` 합성값)
- 재현용 `scripts/scenarios/`

## 관련 레포

- `backend` — 본 에이전트로부터 메트릭을 수집하는 FastAPI/APScheduler
- `diagram-and-docs` — 전체 시스템 설계 문서(서버 풀 명세서 포함)
