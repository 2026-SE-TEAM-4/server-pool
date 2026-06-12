#!/usr/bin/env bash
# 주입된 메트릭 오버라이드를 해제하고 실측값으로 복귀시킨다.
#
# 사용법:
#   ./reset_load.sh 1        # agent-1 만 리셋
#   ./reset_load.sh all      # 전체 리셋
set -euo pipefail

PORT_BASE=9100

[[ $# -eq 0 ]] && { echo "사용법: $0 <서버ID|all>"; exit 1; }

reset_one() {
    local id="$1"
    local port=$((PORT_BASE + id))
    echo ">> agent-${id} (port ${port}) 오버라이드 해제..."
    result=$(curl -sf -X POST "http://localhost:${port}/reset" 2>/dev/null || echo "UNREACHABLE")
    echo "   응답: ${result}"
}

if [[ "$1" == "all" ]]; then
    for id in 1 2 3; do
        reset_one "$id"
    done
else
    reset_one "$1"
fi
