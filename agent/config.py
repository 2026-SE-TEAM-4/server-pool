"""에이전트 환경 설정.

PORT와 SERVER_ID는 컨테이너마다 다르게 주입된다(compose의 environment).
경량 유지를 위해 추가 의존성 없이 os.environ만 사용한다.
"""

import os

PORT = int(os.getenv("PORT", "9101"))
SERVER_ID = int(os.getenv("SERVER_ID", "1"))

# 네트워크 사용률 계산 기준 대역폭(Mbps). 처리량을 이 값 대비 %로 환산한다.
NET_CAP_MBPS = float(os.getenv("NET_CAP_MBPS", "1000"))
# 물리 GPU가 없는 시뮬레이션 환경에서 합성 GPU 사용률을 낼지 여부.
GPU_SIMULATE = os.getenv("GPU_SIMULATE", "true").lower() == "true"
