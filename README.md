# server-pool

서버 예약/할당 관리 시스템의 **서버 풀 에이전트** 레포.
백엔드(APScheduler)가 메트릭을 수집할 대상 서버들을 Docker 컨테이너 N개로
시뮬레이션한다. 모든 컨테이너는 동일한 경량 에이전트 이미지로 기동되며
`:9101/metrics` 를 노출한다.

전체 시스템 설계는 별도 `diagram-and-docs` 레포 참조.

---

## 구조

```text
server-pool/
├── agent/             # 에이전트 패키지 (FastAPI + 메트릭 수집기)
├── scripts/           # 시연·테스트용 bash 시나리오
├── Dockerfile         # 단일 이미지 (stress-ng, hey 포함)
├── docker-compose.yml # N개 인스턴스 기동
└── ...
```

자세한 폴더 책임은 [`tree.md`](./tree.md), 코딩 규칙은 [`rule.md`](./rule.md) 참조.

---

## 실행

```bash
docker compose up -d
```

각 에이전트는 호스트의 `localhost:9101`, `localhost:9102`, ... 로 publish 된다.
백엔드 컨테이너는 `host.docker.internal:910X` 로 수집한다.

확인:

```bash
curl localhost:9101/metrics
curl localhost:9101/health
```

---

## 테스트·시연용 명령

에이전트에는 별도 컨트롤 엔드포인트를 두지 않는다.
모든 장애·부하 시나리오는 외부에서 docker 명령으로 일으킨다.

### 자원 부하 (실제 부하)

```bash
# CPU 코어 4개를 60초간 100%
docker exec agent-3 stress-ng --cpu 4 --timeout 60s

# 메모리 1GB 사용
docker exec agent-3 stress-ng --vm 2 --vm-bytes 1G --timeout 60s
```

### 메트릭 송신 중단

```bash
docker pause agent-3      # 프로세스 동결, /metrics 응답 없음
docker unpause agent-3
```

### 서버 다운

```bash
docker stop agent-3       # connection refused 발생
docker start agent-3
```

### HTTP 트래픽 폭증 (선택)

```bash
hey -z 30s -c 100 http://localhost:9101/metrics
```

### 시나리오 묶음

여러 장애를 조합해 재현 가능한 데모를 만들려면 `scripts/scenarios/` 에 bash
파일로 모아둔다. 한 시나리오 = 한 파일.

```bash
./scripts/scenarios/spike-then-recover.sh
./scripts/scenarios/cascade-failure.sh
```

---

## 관련 레포

- `backend` — 본 에이전트로부터 메트릭을 수집하는 FastAPI/APScheduler
- `frontend` — React SPA
- `diagram-and-docs` — 전체 시스템 설계 문서
