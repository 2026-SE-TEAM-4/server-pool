#!/usr/bin/env bash
# 현재 구동 중인 서버-풀 컨테이너 상태를 보여준다.
set -euo pipefail

COMPOSE_FILE="$(dirname "$0")/../docker-compose.yml"

echo "=== 서버풀 컨테이너 상태 ==="
docker compose -f "$COMPOSE_FILE" ps

echo ""
echo "=== 헬스 체크 ==="
for port in 9101 9102 9103; do
    server_id=$((port - 9100))
    response=$(curl -sf "http://localhost:${port}/health" 2>/dev/null || echo '{"status":"DOWN"}')
    echo "  agent-${server_id} (port ${port}): ${response}"
done

echo ""
echo "=== 현재 메트릭 스냅샷 ==="
for port in 9101 9102 9103; do
    server_id=$((port - 9100))
    response=$(curl -sf "http://localhost:${port}/metrics" 2>/dev/null || echo "UNREACHABLE")
    echo "  agent-${server_id}: ${response}"
done
