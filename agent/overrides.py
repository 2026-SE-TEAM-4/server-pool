"""메트릭 오버라이드 상태.

/inject 로 주입된 값이 있으면 collectors가 실측 대신 이 값을 반환한다.
None이면 오버라이드 없음(실측 사용).
"""

from typing import Optional

cpu: Optional[float] = None
mem: Optional[float] = None
gpu: Optional[float] = None
net: Optional[float] = None
