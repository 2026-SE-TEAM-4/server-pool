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

- 서버(컨테이너) 목록·상태·실시간 메트릭(CPU/RAM/GPU/Net), 임계 색상 표시
- 서버별 CPU/RAM/GPU 되돌리기 / 50% / 100%
- 서버별 모드 토글(안정 합성 / psutil 실측 / 랜덤워크)
- 서버별 자원 기준선(시드) 지정·해제 (stable 모드 중심값)
- 서버 강제 정지 / 재시작
- 카오스 시나리오: 전체 과부하 / 랜덤 정지 / 랜덤 부하 스파이크 / 메모리 누수 / 연쇄 장애 (랜덤 + n분)
- 다크 모던 테마

## 동작 방식

- CPU/RAM/GPU/Net: docker exec로 컨테이너 안 오버라이드 파일(`/tmp/agent_{cpu,mem,gpu,net}_override`)에 값을 쓴다. 에이전트 수집기가 이 파일이 있으면 모드와 무관하게 그 값을 우선 반환한다(없으면 모드별 값). 되돌리기는 파일 삭제.
- 모드 토글: docker exec로 `/tmp/agent_mode`에 모드(stable/real/randomwalk)를 쓴다. 해제(파일 삭제) 시 컨테이너 기본 모드(`DEFAULT_MODE`)로 돌아간다.
- 자원 기준선: docker exec로 `/tmp/agent_{cpu,mem,gpu,net}_baseline`에 값을 써서 stable 모드 중심값을 정한다. 오버라이드와 같은 docker exec 방식이다.
- 도커 수명주기: docker SDK.
