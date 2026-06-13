# server-pool 테스트 툴 (PyQt GUI) 설계

- 날짜: 2026-06-13
- 대상: `server-pool/testtool/` (신규)
- 상태: 승인됨 (구현 계획 작성 전)

## 1. 목적

서버 풀(에이전트 컨테이너 6대)에 테스트용 상황을 GUI로 부여한다. 현재는 에이전트가
실측(psutil) + 합성(GPU) 메트릭만 내보내며 외부에서 부하/장애를 주입할 방법이 없다.
이 툴로 다음을 한다.

- 각 서버(도커 컨테이너) 목록과 상태, 실시간 메트릭(CPU/RAM/GPU/Net) 표시
- 서버별 CPU/RAM/GPU 수치를 **되돌리기 / 50% / 100%** 로 조작
- 서버를 강제 **정지 / 재시작**
- 한 번에 전체를 죽이거나 과부하시키는 **카오스 시나리오**(랜덤 + n분 파라미터화)

## 2. 핵심 설계 결정

### 2.1 메트릭 제어 = "docker exec로 컨테이너 상태 주입"

세 자원을 모두 `docker exec`로 통일한다. 에이전트에 FastAPI 제어 라우터를 추가하지
않는다.

| 자원 | 제어 방식 | 에이전트 변경 |
|------|----------|--------------|
| CPU | `docker exec -d`로 컨테이너 안에서 파이썬 busy-loop 프로세스 기동(목표 부하율 듀티사이클). 중지 = 센티넬 문자열로 `pkill -f`. 이미지에 이미 있는 python만 사용(stress-ng 불필요) | 없음 |
| RAM | `docker exec -d`로 파이썬이 목표 크기 bytearray 할당 후 hold. 중지 = `pkill -f` | 없음 |
| GPU | `docker exec`로 오버라이드 파일(`/tmp/agent_gpu_override`)에 값 기록. 되돌리기 = 파일 삭제 | `gpu.py` 소폭: 파일 있으면 그 값(0~100) 반환, 없으면 기존 합성 로직 |

근거:
- CPU/RAM은 **실부하**라 정확히 50%/100%가 나오지 않는다. psutil은 호스트 전체 코어를
  보므로 컨테이너 부하가 호스트와 경쟁한다. 이 부정확성은 의도된 현실성이다.
- GPU는 에이전트 프로세스 내부의 합성값이라 외부에서 바꾸려면 IPC가 필요하다.
  가장 가벼운 IPC로 "파일 존재 시 읽기"를 택한다. 파일이 없으면 완전히 inert하므로
  운영 이미지에 영향이 없고 플래그 게이팅이 불필요하다.
- stress-ng를 이미지에 넣지 않아 "경량 에이전트" 규칙을 지킨다.

부하 프로세스 식별: `docker exec -d`로 띄우는 명령줄에 고유 센티넬 문자열을 포함시키고,
중지 시 `pkill -f <센티넬>`로 정리한다. CPU/RAM 센티넬을 분리해 자원별로 독립 중지한다.

### 2.2 도커 제어 = docker-py(docker SDK)

컨테이너 목록/상태/start/stop/restart/exec를 docker SDK로 다룬다. compose 프로젝트
라벨(`com.docker.compose.service=agent-N`)로 컨테이너를 발견하고 SERVER_ID·포트
(9100+id)에 매핑한다. 발견 실패 시 config의 고정 매핑으로 폴백한다.

### 2.3 위치 = `server-pool/testtool/`

경량 에이전트(`agent/`)와 의존성을 완전히 분리한다. 자체 `pyproject.toml`
(PyQt6, docker, httpx)을 가진다. 에이전트 이미지에는 포함되지 않는다.

## 3. 모듈 구조

```text
testtool/
├── pyproject.toml          # PyQt6 + docker + httpx
├── README.md
├── app/
│   ├── main.py             # QApplication 진입점
│   ├── config.py           # SERVER_ID↔컨테이너↔포트 매핑, 센티넬, 상수
│   ├── docker_control.py   # docker-py 래퍼: list/status/start/stop/restart/exec
│   ├── agent_client.py     # httpx: /metrics /info /health (오프라인 graceful)
│   ├── load_injector.py    # CPU/RAM 부하 명령 생성·기동·중지, GPU 오버라이드 파일
│   ├── poller.py           # QThreadPool 백그라운드 폴러 (UI 스레드 비차단)
│   ├── scenarios.py        # 카오스 시나리오 정의 + QTimer 기반 러너
│   └── ui/
│       ├── main_window.py      # 전체 레이아웃 조립
│       ├── server_table.py     # 서버 리스트(상태·CPU·RAM·GPU·Net·부하배지)
│       ├── server_panel.py     # 선택 서버 제어(되돌리기/50%/100%, 정지/재시작)
│       ├── scenario_panel.py   # 카오스 시나리오 선택·파라미터·시작/중지
│       └── log_panel.py        # 카오스/액션 로그 스트림
└── tests/                  # load_injector·scenarios·매핑 단위테스트
```

각 모듈 책임:
- `config.py` — 상수와 매핑만. 로직 없음.
- `docker_control.py` — docker-py만 의존. UI/Qt를 모른다. 컨테이너 발견·상태·수명주기·exec.
- `agent_client.py` — httpx만 의존. 에이전트 미응답 시 OFFLINE 표현(예외 삼키지 않고
  명시적 상태 반환).
- `load_injector.py` — 순수 로직(명령 문자열 생성) + docker_control 호출. 명령 생성
  함수는 docker 없이 테스트 가능.
- `poller.py` — QThreadPool/QRunnable로 docker_control·agent_client를 호출하고 Qt
  시그널로 결과 전달.
- `scenarios.py` — 시나리오 정의 + 러너(QTimer 상태머신). 스텝 결정은 시드 고정 RNG로
  결정론적.
- `ui/*` — 위젯. 상태를 직접 만들지 않고 시그널로 받는다.

## 4. 데이터 흐름 / 스레딩

```
QThreadPool 폴러 (2~3초 주기)
  ├─ docker-py: 컨테이너 상태(running/exited/restarting)
  └─ httpx: 각 에이전트 /metrics  →  signal로 UI 테이블 갱신
사용자 클릭 / 시나리오 러너
  └─ docker_control · load_injector 액션도 풀에서 실행(블로킹 호출이 UI 비차단)
```

docker/HTTP 호출은 전부 블로킹이므로 UI 스레드에서 직접 호출하지 않는다. QThreadPool
워커에서 실행하고 Qt 시그널로 결과를 돌려받는다. 이것이 GUI 프리징 방지의 핵심이다.

## 5. 서버 상태 모델

테이블 한 행이 표현하는 상태:
- SERVER_ID, hostname(/info에서)
- 컨테이너 상태: running / exited / restarting (docker-py)
- 에이전트 도달성: /health 성공 여부 (정지 시 OFFLINE)
- 현재 메트릭: CPU / RAM / GPU / Net (/metrics, 미응답 시 `-`)
- 주입 중인 부하 배지: CPU / RAM / GPU 오버라이드 활성 표시
- 카오스 대상 여부

## 6. 카오스 시나리오 (3종)

모두 "랜덤 + n분" 파라미터화. 러너는 QTimer 상태머신이며 시작 시 종료 시각을 잡고
매 틱 다음 액션을 결정·로그한다. **중지 시 진행 중인 모든 부하·정지를 즉시 원복**한다.

1. 전체 과부하 — 실행 중 모든 서버에 CPU/RAM 고부하를 N분 주입 후 자동 되돌리기.
2. 랜덤 정지 — 랜덤 서버를 랜덤 시간(설정 구간, 예 10~60초) 정지 후 재시작, N분 반복.
3. 랜덤 부하 스파이크 — 랜덤 서버에 랜덤 강도/시간 부하를 N분 동안 산발적으로.

파라미터: 지속(분), 정지 구간(초 min~max), 부하 강도(%).

## 7. 에이전트 변경 (최소)

`agent/collectors/gpu.py`에 오버라이드 파일 처리만 추가한다.

- 상수 경로 `GPU_OVERRIDE_PATH = "/tmp/agent_gpu_override"`.
- `read_gpu_usage()` 시작에서 파일이 있으면 내용을 0~100 float로 파싱해 반환.
  파싱 실패/범위 밖이면 무시하고 기존 로직 진행.
- 파일이 없으면 기존 합성 로직 그대로(완전 inert).
- GPU 미탑재 서버(gpu_model None)는 GPU_SIMULATE=false라 항상 None — 오버라이드도
  무시(일관성: 없는 GPU를 만들어내지 않음).

`tree.md`에 `testtool/` 추가 및 gpu.py 주석 갱신.

## 8. 테스트

비-UI 로직 중심(docker-py mock):
- `load_injector`: CPU/RAM 부하 명령 문자열, GPU 오버라이드 set/clear 명령 생성.
- `scenarios`: 시드 고정 RNG로 스텝 결정 결정론 검증(어떤 서버를 언제 정지/원복).
- 컨테이너↔SERVER_ID 매핑 파싱(compose 라벨·이름 → id·포트).
- 에이전트 gpu 오버라이드: 파일 있을 때/없을 때/잘못된 값일 때 반환값(server-pool
  기존 tests에 추가).

UI는 스모크 수준(pytest-qt 선택, 위젯 생성·시그널 연결 정도).

## 9. YAGNI로 제외

- 네트워크(Net) 직접 제어 — 실트래픽 생성이 까다로워 v1 제외. 동일 오버라이드 파일
  패턴으로 후속 확장 가능. Net은 실측 그대로 표시.
- 에이전트 FastAPI 제어 라우터 — docker-exec 통일로 불필요.
- 부하 강도의 정밀 보정 — 실부하의 자연스러운 부정확성을 유지.
