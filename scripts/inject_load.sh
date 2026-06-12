#!/usr/bin/env bash
# 특정 서버의 메트릭 값을 강제로 오버라이드한다 (실제 부하 없이 수치만 변경).
#
# 사용법:
#   ./inject_load.sh <서버ID> <프리셋>
#   ./inject_load.sh <서버ID> custom <cpu> <mem> [gpu] [net]
#
# 프리셋:
#   full       CPU=100 MEM=100 GPU=100 NET=100
#   high       CPU=90  MEM=85  GPU=80  NET=70
#   medium     CPU=70  MEM=70  GPU=70  NET=50
#   low        CPU=20  MEM=30  GPU=15  NET=10
#   idle       CPU=5   MEM=20  GPU=0   NET=2
#   cpu-spike  CPU=100 MEM=40  GPU=30  NET=20
#   mem-spike  CPU=20  MEM=100 GPU=30  NET=20
#   gpu-spike  CPU=20  MEM=40  GPU=100 NET=20
#   net-spike  CPU=20  MEM=40  GPU=30  NET=100
#
# 예시:
#   ./inject_load.sh 1 full
#   ./inject_load.sh 2 cpu-spike
#   ./inject_load.sh 3 custom 75 60 50 30
#   ./inject_load.sh all high
set -euo pipefail

PORT_BASE=9100

usage() {
    echo "사용법: $0 <서버ID|all> <프리셋|custom> [cpu mem [gpu net]]"
    echo "프리셋: full | high | medium | low | idle | cpu-spike | mem-spike | gpu-spike | net-spike"
    exit 1
}

[[ $# -lt 2 ]] && usage

TARGET="$1"
PRESET="$2"

case "$PRESET" in
    full)       CPU=100; MEM=100; GPU=100; NET=100 ;;
    high)       CPU=90;  MEM=85;  GPU=80;  NET=70  ;;
    medium)     CPU=70;  MEM=70;  GPU=70;  NET=50  ;;
    low)        CPU=20;  MEM=30;  GPU=15;  NET=10  ;;
    idle)       CPU=5;   MEM=20;  GPU=0;   NET=2   ;;
    cpu-spike)  CPU=100; MEM=40;  GPU=30;  NET=20  ;;
    mem-spike)  CPU=20;  MEM=100; GPU=30;  NET=20  ;;
    gpu-spike)  CPU=20;  MEM=40;  GPU=100; NET=20  ;;
    net-spike)  CPU=20;  MEM=40;  GPU=30;  NET=100 ;;
    custom)
        [[ $# -lt 4 ]] && { echo "custom 사용법: $0 <ID> custom <cpu> <mem> [gpu] [net]"; exit 1; }
        CPU="$3"; MEM="$4"
        GPU="${5:-50}"; NET="${6:-20}"
        ;;
    *) echo "알 수 없는 프리셋: $PRESET"; usage ;;
esac

inject_one() {
    local id="$1"
    local port=$((PORT_BASE + id))
    local payload="{\"cpu\":${CPU},\"mem\":${MEM},\"gpu\":${GPU},\"net\":${NET}}"
    echo ">> agent-${id} (port ${port}) 오버라이드 주입: CPU=${CPU}% MEM=${MEM}% GPU=${GPU}% NET=${NET}%"
    result=$(curl -sf -X POST "http://localhost:${port}/inject" \
        -H "Content-Type: application/json" \
        -d "$payload" 2>/dev/null || echo "UNREACHABLE")
    echo "   응답: ${result}"
}

if [[ "$TARGET" == "all" ]]; then
    for id in 1 2 3; do
        inject_one "$id"
    done
else
    inject_one "$TARGET"
fi
