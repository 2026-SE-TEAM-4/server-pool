# server-pool 디렉토리 구조

본 레포는 백엔드가 메트릭을 수집할 대상 "서버 풀"을 시뮬레이션한다.
한 종류의 경량 에이전트 이미지를 Docker 컨테이너로 여러 개 띄워
N대의 관리 대상 서버를 흉내낸다. 각 컨테이너는 `:9101/metrics` 를 노출한다.

파일은 기능 추가에 따라 계속 바뀌지만, 아래 디렉토리 구조는 가능한 고정한다.
새 파일을 추가하기 전에 어느 폴더에 속하는지 본 문서로 확인한다.
구조 자체를 바꿀 필요가 생기면 코드보다 먼저 본 문서를 갱신한다.

```text
server-pool/
├── agent/                     # 에이전트 패키지 (모든 코드는 이 안)
│   ├── main.py                # FastAPI entrypoint (/metrics, /health, /info)
│   ├── config.py              # 환경 설정 (SERVER_ID, PORT, NET_CAP_MBPS, GPU_SIMULATE, DEFAULT_MODE, SERVER_SPECS)
│   ├── sim.py                 # 모드 판정·공용 파일 리더·평균회귀(MeanRevertSim)
│   └── collectors/            # 메트릭 수집기 (1 자원 = 1 파일)
│                              # cpu.py, memory.py, net.py, gpu.py
│                              # 값 우선순위: override > stable > real > randomwalk
├── testtool/                  # PyQt GUI 테스트 콘솔 (에이전트와 의존성 분리)
│   ├── app/                   # config·docker_control·agent_client·load_injector
│   │                          # sim_control(모드·기준선 제어)·poller·scenarios
│   │                          # ui/ (부하·장애·카오스 주입, sim_panel·theme 포함)
│   ├── tests/                 # 비-UI 로직 단위 테스트
│   ├── pyproject.toml         # PyQt6·docker·httpx (에이전트 의존성과 분리)
│   └── README.md
├── tests/                     # 수집기 단위 테스트 (test_collectors.py)
├── pyproject.toml             # uv 기반 의존성·도구 설정
├── Dockerfile                 # 에이전트 단일 이미지
├── docker-compose.yml         # 6개 인스턴스 기동 (agent-1..6, 포트 9101..9106)
├── README.md
├── CLAUDE.md                  # 작업 시작 시 참조
├── tree.md                    # 본 파일
└── rule.md                    # 코딩 규칙
```

## 설계 원칙

- 에이전트는 **경량**이 우선이다. 백엔드와 의존성을 공유하지 않는다.
- `collectors/` 의 각 파일은 단일 자원만 다룬다 (CPU, 메모리, GPU 등).
  새로운 자원이 추가되면 파일을 추가하고, 기존 파일을 부풀리지 않는다.
- 백엔드와의 인터페이스(메트릭 JSON 스키마, 엔드포인트 규약)는
  `diagram-and-docs` 또는 별도 contract 위치를 단일 출처로 삼는다.
  스키마를 본 레포에서 임의로 변경하지 않는다.
- `testtool/` 은 운영 에이전트가 아니라 개발/시연용 GUI 부하·장애 주입 콘솔이다.
  에이전트 이미지에 포함되지 않으며 호스트에서 직접 실행한다(docker 소켓·퍼블리시 포트 사용).
  CPU/RAM/GPU 제어는 docker exec로 오버라이드 파일을 써서 수집기 값을 덮는 방식으로 통일한다.
  모드 토글(`/tmp/agent_mode`)·자원별 기준선(`/tmp/agent_{cpu,mem,gpu,net}_baseline`)도
  오버라이드 파일과 동일하게 docker exec로 써서 제어한다.
