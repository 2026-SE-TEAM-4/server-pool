# server-pool

서버 예약/할당 관리 시스템의 **서버 풀 에이전트**.
백엔드(APScheduler)가 메트릭을 수집할 대상 서버들을 동일한 경량 에이전트 이미지
N개로 시뮬레이션한다. 각 컨테이너는 `:91xx`의 `/metrics`·`/health`를 노출한다.

> **현재 상태: 기초공사 단계.** 부팅·`/health`·`/metrics`(자리값)까지만 있다.
> 실제 메트릭 수집 로직과 JSON 계약은 단일 출처(설계 문서) 확정 후 구현하며,
> 본 레포에서 계약을 임의로 확정하지 않는다.

## 구성

- 기본 3대: `agent-1`·`agent-2`·`agent-3`, 호스트 포트 9101·9102·9103.
- 각 인스턴스는 `SERVER_ID`·`PORT`를 compose에서 주입받는다.
- 백엔드 컨테이너는 `host.docker.internal:9101..9103`으로 수집한다(수집은 후속).

## 실행

```bash
docker compose up --build -d
curl localhost:9101/health     # {"status":"ok"}
curl localhost:9101/metrics    # 자리값 JSON
```

대수를 늘리려면 compose에 `agent-4` … 를 같은 형식(고정 포트 publish)으로 추가한다.

## 환경 변수

| 키 | 기본 | 설명 |
| --- | --- | --- |
| PORT | 9101 | 에이전트 listen 포트 |
| SERVER_ID | 1 | 에이전트 식별(인스턴스별 주입) |

## 장애·부하 시연 (이미지에 stress-ng·hey 포함)

에이전트에는 별도 컨트롤 엔드포인트를 두지 않는다. 모든 시나리오는 외부 docker 명령으로 일으킨다.

```bash
docker compose exec agent-3 stress-ng --cpu 4 --timeout 60s              # CPU 부하
docker compose exec agent-3 stress-ng --vm 2 --vm-bytes 1G --timeout 60s # 메모리
docker pause agent-3   # 메트릭 송신 중단 (docker unpause 로 복구)
docker stop agent-3    # 서버 다운 (docker start 로 복구)
hey -z 30s -c 100 http://localhost:9101/metrics                          # 트래픽 폭증
```

## 후속(미구현)

`agent/collectors/`(자원별 실제 수집), 메트릭 JSON 계약, 재현용 `scripts/scenarios/`.

## 관련 레포

- `backend` — 본 에이전트로부터 메트릭을 수집하는 FastAPI/APScheduler
- `diagram-and-docs` — 전체 시스템 설계 문서
