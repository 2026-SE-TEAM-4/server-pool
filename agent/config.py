"""에이전트 환경 설정.

PORT와 SERVER_ID는 컨테이너마다 다르게 주입된다(compose의 environment).
경량 유지를 위해 추가 의존성 없이 os.environ만 사용한다.
"""

import os

PORT = int(os.getenv("PORT", "9101"))
SERVER_ID = int(os.getenv("SERVER_ID", "1"))
