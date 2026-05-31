#!/bin/bash
# Armada Random Sum Demo
# Creates 3 workers, each waits 60-120s and returns a random number.
# Orchestrator sums them and prints the result.
#
# Usage: armada start && bash demos/random-sum.sh

set -euo pipefail

API="http://127.0.0.1:9100"
PROJECT="random-sum"
WORKDIR="/tmp/armada-randomsum"

echo "=== Armada Random Sum ==="
echo ""

mkdir -p "$WORKDIR"

curl -s -X POST "$API/api/project-labels" -H "Content-Type: application/json" \
    -d "{\"id\":\"$PROJECT\",\"name\":\"Random Sum\",\"path\":\"$WORKDIR\"}" > /dev/null

curl -s -X POST "$API/api/nodes" -H "Content-Type: application/json" \
    -d "{\"name\":\"Summer\",\"project_label_id\":\"$PROJECT\",\"agent_type\":\"bash\"}" > /dev/null

echo "Orchestrator: Summer (id=1)"
echo ""

id() {
    curl -s -X POST "$API/api/nodes" -H "Content-Type: application/json" \
        -d "{\"name\":\"$1\",\"parent_id\":1,\"project_label_id\":\"$PROJECT\",\"agent_type\":\"bash\"}" | \
        python3 -c "import sys,json; print(json.load(sys.stdin)['id'])"
}

echo "Spawning workers..."
W1=$(id "Random-1")
echo "  Random-1 (id=$W1)"
W2=$(id "Random-2")
echo "  Random-2 (id=$W2)"
W3=$(id "Random-3")
echo "  Random-3 (id=$W3)"

echo ""
echo "Assigning tasks to workers..."

tmux send-keys -t "armada:Random-1" \
    "armada-node-report active 'generating' && sleep \$((60 + RANDOM % 61)) && N=\$RANDOM && armada-node-result \"\$N\" && echo \"Random-1: \$N\"" Enter

tmux send-keys -t "armada:Random-2" \
    "armada-node-report active 'generating' && sleep \$((60 + RANDOM % 61)) && N=\$RANDOM && armada-node-result \"\$N\" && echo \"Random-2: \$N\"" Enter

tmux send-keys -t "armada:Random-3" \
    "armada-node-report active 'generating' && sleep \$((60 + RANDOM % 61)) && N=\$RANDOM && armada-node-result \"\$N\" && echo \"Random-3: \$N\"" Enter

echo ""
echo "Waiting for workers to finish..."
echo "(This takes 60-120 seconds — watch the dashboard!)"
echo ""
echo "Dashboard: $API"
echo ""

TIMEOUT=180
ELAPSED=0
while [ "$ELAPSED" -lt "$TIMEOUT" ]; do
    R1=$(curl -s "$API/api/nodes/$W1" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['node']['status'])" 2>/dev/null || echo "unknown")
    R2=$(curl -s "$API/api/nodes/$W2" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['node']['status'])" 2>/dev/null || echo "unknown")
    R3=$(curl -s "$API/api/nodes/$W3" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['node']['status'])" 2>/dev/null || echo "unknown")

    if [ "$R1" = "idle" ] && [ "$R2" = "idle" ] && [ "$R3" = "idle" ]; then
        echo ""
        echo "All workers finished!"

        A=$(cat "/tmp/armada-results/Random-1/result" 2>/dev/null || echo "0")
        B=$(cat "/tmp/armada-results/Random-2/result" 2>/dev/null || echo "0")
        C=$(cat "/tmp/armada-results/Random-3/result" 2>/dev/null || echo "0")
        SUM=$((A + B + C))

        echo ""
        echo "  Random-1: $A"
        echo "  Random-2: $B"
        echo "  Random-3: $C"
        echo "  ═══════════════════"
        echo "  SUM: $SUM"
        echo ""

        curl -s -X POST "$API/api/report" -H "Content-Type: application/json" \
            -d "{\"name\":\"Summer\",\"status\":\"idle\",\"message\":\"SUM: $SUM\"}" > /dev/null

        curl -s -X DELETE "$API/api/nodes/$W1" > /dev/null
        curl -s -X DELETE "$API/api/nodes/$W2" > /dev/null
        curl -s -X DELETE "$API/api/nodes/$W3" > /dev/null

        echo "Workers killed. Done."
        break
    fi

    echo -n "."
    sleep 5
    ELAPSED=$((ELAPSED + 5))
done

if [ "$ELAPSED" -ge "$TIMEOUT" ]; then
    echo "Timeout! Some workers didn't finish in time."
fi

echo ""
