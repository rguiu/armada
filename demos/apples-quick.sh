#!/bin/bash
# Armada Apples Demo — Quick Test (10-20s)
# Orchestrator spawns 3 workers. Each waits, produces a random number.
# Orchestrator sums them and announces.

set -euo pipefail
API="http://127.0.0.1:9100"
PROJECT="apples-quick"
WORKDIR="/tmp/armada-apples-q"

echo "=== Armada Apples Demo ==="

# Cleanup previous instances
armada stop 2>/dev/null || kill $(lsof -ti :9100) 2>/dev/null || true
tmux kill-server 2>/dev/null || true
rm -rf "$WORKDIR"
mkdir -p "$WORKDIR"

armada start
sleep 2

curl -s -X POST "$API/api/project-labels" -H "Content-Type: application/json" \
    -d "{\"id\":\"$PROJECT\",\"name\":\"Apples Quick\",\"path\":\"$WORKDIR\"}" > /dev/null

curl -s -X POST "$API/api/nodes" -H "Content-Type: application/json" \
    -d "{\"name\":\"Orchard\",\"project_label_id\":\"$PROJECT\",\"agent_type\":\"bash\"}" > /dev/null

echo "Orchestrator ready."

# Spawn 3 workers
id() { curl -s -X POST "$API/api/nodes" -H "Content-Type: application/json" -d '{"name":"'"$1"'","parent_id":1,"project_label_id":"'"$PROJECT"'","agent_type":"bash"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])"; }
W1=$(id "Apple-1")
W2=$(id "Apple-2")
W3=$(id "Apple-3")
echo "Workers: Apple-1=$W1 Apple-2=$W2 Apple-3=$W3"

# Assign tasks
sleep 1
tmux send-keys -t "armada:Apple-1" \
    "armada-node-report active 'picking apples' && sleep 3 && N=\$((RANDOM % 11 + 10)) && armada-node-result \$N && echo 'Apple-1 done: '\$N" Enter
sleep 0.3
tmux send-keys -t "armada:Apple-2" \
    "armada-node-report active 'picking apples' && sleep 3 && N=\$((RANDOM % 11 + 10)) && armada-node-result \$N && echo 'Apple-2 done: '\$N" Enter
sleep 0.3
tmux send-keys -t "armada:Apple-3" \
    "armada-node-report active 'picking apples' && sleep 3 && N=\$((RANDOM % 11 + 10)) && armada-node-result \$N && echo 'Apple-3 done: '\$N" Enter

echo "Waiting for workers to finish..."
for i in $(seq 1 30); do
    S1=$(curl -s "$API/api/nodes/$W1" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['node']['status'])" 2>/dev/null || echo "?")
    S2=$(curl -s "$API/api/nodes/$W2" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['node']['status'])" 2>/dev/null || echo "?")
    S3=$(curl -s "$API/api/nodes/$W3" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['node']['status'])" 2>/dev/null || echo "?")

    if [ "$S1" = "idle" ] && [ "$S2" = "idle" ] && [ "$S3" = "idle" ]; then
        sleep 1  # Let result files flush
        A=$(cat "/tmp/armada-results/Apple-1/result" 2>/dev/null || echo "0")
        B=$(cat "/tmp/armada-results/Apple-2/result" 2>/dev/null || echo "0")
        C=$(cat "/tmp/armada-results/Apple-3/result" 2>/dev/null || echo "0")
        SUM=$((A + B + C))
        echo ""
        echo "  Apple-1: $A | Apple-2: $B | Apple-3: $C"
        echo "  ═══════════════════"
        echo "  I have $SUM apples"
        armada-node-report active "I have $SUM apples" 2>/dev/null || true
        curl -s -X DELETE "$API/api/nodes/$W1" > /dev/null
        curl -s -X DELETE "$API/api/nodes/$W2" > /dev/null
        curl -s -X DELETE "$API/api/nodes/$W3" > /dev/null
        echo ""
        break
    fi
    echo -n "."
    sleep 2
done

echo "Dashboard: http://127.0.0.1:9100"
