#!/usr/bin/env bash
# 지정한 서버를 강제로 종료(SIGKILL)한다.
#
# 사용법:
#   ./crash.sh 1          # agent-1 강제 종료
#   ./crash.sh 2 3        # agent-2, agent-3 강제 종료
#   ./crash.sh all        # 전체 종료
#
# 재기동: docker compose up -d agent-1
set -euo pipefail

COMPOSE_FILE="$(dirname "$0")/../docker-compose.yml"

if [[ $# -eq 0 ]]; then
    echo "사용법: $0 <서버ID...>  (예: $0 1  또는  $0 2 3  또는  $0 all)"
    exit 1
fi

crash_server() {
    local id="$1"
    local container="server-pool-agent-${id}-1"
    echo ">> agent-${id} (${container}) 강제 종료..."
    if docker kill "$container" 2>/dev/null; then
        echo "   OK: ${container} killed"
    else
        echo "   SKIP: ${container} 가 없거나 이미 정지됨"
    fi
}

if [[ "$1" == "all" ]]; then
    for id in 1 2 3; do
        crash_server "$id"
    done
else
    for id in "$@"; do
        crash_server "$id"
    done
fi

echo ""
echo "=== 현재 상태 ==="
docker compose -f "$COMPOSE_FILE" ps
