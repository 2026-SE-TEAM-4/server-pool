# server-pool 테스트 콘솔

서버 풀 에이전트 컨테이너에 부하/장애/카오스 상황을 GUI로 주입하는 PyQt 데스크톱 툴.

## 사전 준비

먼저 서버 풀을 띄운다:

    cd server-pool
    docker compose up --build -d

## 실행

    cd server-pool/testtool
    uv sync
    uv run python -m app.main

## 기능

- 서버(컨테이너) 목록·상태·실시간 메트릭(CPU/RAM/GPU/Net)
- 서버별 CPU/RAM/GPU 되돌리기 / 50% / 100%
- 서버 강제 정지 / 재시작
- 카오스 시나리오: 전체 과부하 / 랜덤 정지 / 랜덤 부하 스파이크 (랜덤 + n분)

## 동작 방식

- CPU/RAM: docker exec로 컨테이너 안 파이썬 부하 프로세스 기동(실부하). 중지는 센티넬 pkill.
- GPU: docker exec로 오버라이드 파일(`/tmp/agent_gpu_override`) 기록. 에이전트 gpu 수집기가 읽는다.
- 도커 수명주기: docker SDK.

> 실부하라 CPU/RAM은 정확히 50%/100%가 되지 않는다(의도된 현실성). RAM은 호스트 OOM 방지를 위해 안전 예산(config.RAM_LOAD_MB_PER_100) 내에서만 할당한다.
