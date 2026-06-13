# server-pool 듀얼 모드 + testtool 확장 설계

작성일: 2026-06-13

## 배경과 목적

server-pool 에이전트는 현재 `METRIC_SIMULATE` 환경변수로 두 동작(랜덤워크 시뮬 / psutil 실측)을
가지며, testtool이 `/tmp/agent_*_override` 파일을 docker exec로 써서 값을 강제하는 메커니즘이 있다.

문제: 데모·테스트에서 수치를 의도대로 조정하기 어렵다. 기본 랜덤워크는 매 틱 CPU ±8%로
크게 출렁여 곡선이 거칠고, 실측은 호스트 /proc에 묶여 통제가 안 된다.

목표: **가짜이지만 안정적인 합성 메트릭**을 기본(메인) 모드로 만든다. 기존 동작은
docker exec로만 켜는 서브 모드로 내린다. testtool에 모드 전환·서버별 기준선(시드) 지정·
실무형 카오스 시나리오·다크 모던 테마를 추가한다.

`/metrics` JSON 스키마(cpuUsage/memUsage/gpuUsage/netUsage/status)는 **변경하지 않는다**.
백엔드 수집 계약·명세서(diagram-and-docs)는 영향받지 않는다.

## 모드 모델 (컨테이너 단위·파일 토글)

`/tmp/agent_mode` 파일 하나가 컨테이너의 모드를 결정한다. 파일이 없거나 알 수 없는 값이면
기본값 `stable`. 컨테이너 재시작 시 파일이 사라지므로 항상 `stable`로 복귀한다(설정 초기화).

| 모드 | 분류 | 동작 |
|------|------|------|
| `stable` | 메인(기본) | 자원별 기준선 중심 평균회귀. 매 틱 0.5~2% 드리프트. 가짜·안정 |
| `real` | 서브 | psutil 실측 (기존 `METRIC_SIMULATE=false`) |
| `randomwalk` | 서브 | 기존 ±8% 랜덤워크 (기존 `METRIC_SIMULATE=true`) |

- `METRIC_SIMULATE` 환경변수는 제거하고 `DEFAULT_MODE`(기본 `stable`)로 대체한다.
  파일이 없을 때 적용할 기본 모드를 정한다. 베어메탈 배포는 `DEFAULT_MODE=real`.

## 자원별 값 우선순위 (모든 모드 공통)

각 메트릭(cpu/mem/gpu/net)을 읽을 때 순서대로 판정한다.

```
1. override 파일 있으면      → 그 값 (절대 고정, 모든 모드 최우선)  ← 부하/카오스 주입용
2. mode == stable           → 기준선 중심 드리프트
3. mode == real             → psutil 실측
4. mode == randomwalk       → ±8% 랜덤워크
```

이 우선순위 덕분에 기존 testtool 부하/카오스 주입(50%/100%)은 어느 모드에서든 그대로 동작한다.
GPU는 GPU 미탑재 서버(spec.gpu_model is None)에서는 항상 None을 반환한다(기존 규약 유지).

## 기준선(시드값) — stable 모드

- 각 자원의 시드 기준선: 기존처럼 `SERVER_ID` 해시로 결정해 서버마다 다른 곡선을 유지한다.
- 자원별 기준선 파일(`/tmp/agent_cpu_baseline`, `_mem_baseline`, `_gpu_baseline`,
  `_net_baseline`)이 있으면 그 값을 기준선으로 쓴다. 이것이 "서버별 시드값 지정"이다.
- 평균회귀 드리프트:
  ```
  step  = rng.uniform(0.5, 2.0) * 방향(±1)
  pull  = (기준선 - 현재값) * 0.15
  현재값 = clamp(현재값 + step + pull, 하한, 상한)
  ```
  시작값은 기준선. 기준선에서 멀어지면 pull이 되돌려 장시간 기준선 근처에서 잔잔히 흔들린다.
  자원별 하한/상한은 기존 값을 따른다(CPU 5~95, MEM 10~90, GPU 0~100, NET 0~100).

## 코드 구조 — agent

- 신규 `agent/sim.py`
  - `current_mode(default="stable") -> str` : `/tmp/agent_mode` 읽기, 유효 모드만 허용.
  - `read_pct_file(path) -> float | None` : override·baseline 공용 리더(0~100 클램프).
    지금 cpu/mem/gpu에 복붙된 `_read_override`를 여기로 통합(DRY).
  - `class MeanRevertSim` : 시드 키·기준선·하한/상한·pull을 받아 `step(baseline)` 제공.
- `collectors/{cpu,mem,gpu,net}.py` : 위 우선순위대로 얇게 재작성.
  `net.py`도 모드를 따른다(stable=합성 드리프트, real=psutil 실측 throughput, randomwalk=소폭 워크).
- `config.py` : `DEFAULT_MODE` 추가, `METRIC_SIMULATE` 제거.
- 경로 상수: 각 collector가 override·baseline 경로를 보유(테스트가 참조).

## 코드 구조 — testtool

- 신규 `app/sim_control.py`
  - 순수 `build_mode_cmd(mode)`, `build_set_baseline_cmd(path, pct)`, `build_clear_cmd(path)`.
  - `class SimControl` : `set_mode` / `set_baseline` / `clear_baseline`(docker exec 디스패치).
- `app/config.py` : mode 경로, 자원별 baseline 경로, NET override 경로 추가.
- `app/load_injector.py` : `apply_net` / `clear_net` 추가(NET override 파일).
- 신규 `app/ui/sim_panel.py`
  - 선택 서버 모드 토글(안정 합성 / psutil 실측 / 랜덤워크).
  - 자원별 기준선(시드) 슬라이더 CPU/RAM/GPU/Net + 적용/해제.
  - 시그널만 emit, 실행은 main_window가 워커로 디스패치(기존 패턴 동일).
- `app/ui/main_window.py` : sim_panel 배선 추가.

## 카오스 시나리오 2개 추가 (실무형)

순수 결정 엔진(`tick(elapsed, running, rng) -> [Action]`) 패턴을 따른다. 시드 고정 시 결정론적.
점진 변화는 엔진이 틱마다 증가하는 값을 `load_*` Action으로 내보내 구현한다.

1. 메모리 누수 → OOM 재시작 (`MemoryLeak`)
   - 대상 서버 1대의 RAM을 시작값에서 ~99%까지 지속 시간 동안 선형 상승(load_ram).
   - 임계 도달 시 컨테이너 stop(OOM 모사) 후 잠시 뒤 start, override revert.
   - 백엔드 메모리 이상탐지·장애예측·점검 전환 잡을 자극.

2. 연쇄 장애 (`CascadingFailure`)
   - 서버 1대 stop → 남은 running 서버의 CPU/RAM을 단계적으로 끌어올림(부하 재분배 모사).
   - 임계 초과 시 다음 서버도 위험 상태로. 지속 시간 만료 시 전체 revert·start.
   - 이상 상관분석·인시던트 묶기·건강점수 잡을 자극.

Action 종류에 `load_net` 추가(트래픽 동반 상승 표현용). 기존 `gpu` dispatch 활용.
ScenarioPanel·main_window의 시나리오 목록과 파라미터 폼에 두 항목을 추가한다.

## testtool 테마 (다크·모던)

- 신규 `app/ui/theme.py` : QSS 문자열 + 색 상수. `main.py`에서 `app.setStyleSheet`로 전역 적용.
- 다크 팔레트(배경/표면/경계/텍스트/뮤트) + 액센트 컬러. 라운드 8px, hover/focus 상태,
  그룹박스·버튼·스핀박스·콤보·테이블 일관 스타일.
- 메트릭 임계 색상: 정상(녹)·경고(황)·위험(적). `server_table`에 threshold 컬러링 추가.

## 테스트

- agent `tests/test_collectors.py`
  - override가 모든 모드에서 최우선.
  - stable 모드 드리프트가 하한/상한 안에 머물고 기준선 근처를 유지.
  - 모드 파일 전환이 동작(stable/real/randomwalk).
  - 기준선 파일이 드리프트 중심을 바꿈.
  - GPU 미탑재 서버는 항상 None.
- testtool `tests/`
  - `build_mode_cmd`·`build_set_baseline_cmd`·`build_clear_cmd` 순수 함수.
  - `MemoryLeak`·`CascadingFailure` 엔진 tick을 시드 고정 RNG로 결정론 검증.

## 문서

- `server-pool/tree.md` : 신규 파일(agent/sim.py, testtool app/sim_control.py, ui/sim_panel.py,
  ui/theme.py) 반영.
- `server-pool/README.md`, `server-pool/testtool/README.md` : 모드·기준선·신규 시나리오·테마 설명.
- 루트 `CLAUDE.md` : `METRIC_SIMULATE` → 모드 모델(`DEFAULT_MODE`) 갱신.

## 범위 밖 (YAGNI)

- 실제 GPU 노드 연동.
- 설정 영속화(재시작 후 유지) — 의도적으로 초기화.
- CLI 제어 도구 — GUI만.
- `/metrics` 스키마·백엔드 계약 변경.
