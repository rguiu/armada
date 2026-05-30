#!/bin/bash
# Armada Apples Demo
# Orchestrator spawns 3 workers in parallel. Each waits a random time,
# returns a random number. Orchestrator sums them and announces.
#
# Usage: armada start && bash demos/apples.sh

set -euo pipefail

API="http://127.0.0.1:9100"
PROJECT="apples-demo"
WORKDIR="/tmp/armada-apples"

echo "=== Armada Apples Demo ==="
echo ""

# Cleanup
tmux kill-server 2>/dev/null || true
rm -rf "$WORKDIR"
mkdir -p "$WORKDIR"

# -- Setup project and orchestrator --
armada start
sleep 2

mkdir -p "$WORKDIR"
curl -s -X POST "$API/api/project-labels" -H "Content-Type: application/json" \
    -d "{\"id\":\"$PROJECT\",\"name\":\"Apples Demo\",\"path\":\"$WORKDIR\"}" > /dev/null

curl -s -X POST "$API/api/nodes" -H "Content-Type: application/json" \
    -d "{\"name\":\"Orchard\",\"project_label_id\":\"$PROJECT\",\"agent_type\":\"bash\"}" > /dev/null

echo "Orchestrator: Orchard (id=1)"
echo ""

# Attach to Orchard and run the orchestration
# We simulate what the user would type in the attached terminal:

# Step 1: Spawn 3 worker nodes
echo "Spawning workers..."
W1=$(curl -s -X POST "$API/api/nodes" -H "Content-Type: application/json" \
    -d '{"name":"Apple-1","parent_id":1,"project_label_id":"apples-demo","agent_type":"bash"}' | \
    python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "  Apple-1 (id=$W1)"

W2=$(curl -s -X POST "$API/api/nodes" -H "Content-Type: application/json" \
    -d '{"name":"Apple-2","parent_id":1,"project_label_id":"apples-demo","agent_type":"bash"}' | \
    python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "  Apple-2 (id=$W2)"

W3=$(curl -s -X POST "$API/api/nodes" -H "Content-Type: application/json" \
    -d '{"name":"Apple-3","parent_id":1,"project_label_id":"apples-demo","agent_type":"bash"}' | \
    python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "  Apple-3 (id=$W3)"

# Step 2: Give each worker a command (via tmux send-keys)
echo ""
echo "Assigning tasks to workers..."

# Worker 1: wait 60+rand(10-50)s, report random 10-20
tmux send-keys -t "armada:Apple-1" \
    "sleep \$((60 + RANDOM % 41 + 10)) && N=\$((RANDOM % 11 + 10)) && armada_report_result \"\$N\" && echo \"Apple-1: \$N apples\"" Enter

# Worker 2
tmux send-keys -t "armada:Apple-2" \
    "sleep \$((60 + RANDOM % 41 + 10)) && N=\$((RANDOM % 11 + 10)) && armada_report_result \"\$N\" && echo \"Apple-2: \$N apples\"" Enter

# Worker 3
tmux send-keys -t "armada:Apple-3" \
    "sleep \$((60 + RANDOM % 41 + 10)) && N=\$((RANDOM % 11 + 10)) && armada_report_result \"\$N\" && echo \"Apple-3: \$N apples\"" Enter

# Step 3: Coordinator (Orchard) waits for all workers
echo ""
echo "Orchard waiting for workers to finish..."
echo "(This takes ~60-100 seconds — watch the dashboard!)"
echo ""
echo "Dashboard: $API"
echo ""

# Wait loop on the API side
TIMEOUT=150
ELAPSED=0
while [ "$ELAPSED" -lt "$TIMEOUT" ]; do
    # Check all 3 workers
    R1=$(curl -s "$API/api/nodes/$W1" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['node']['status'])" 2>/dev/null || echo "unknown")
    R2=$(curl -s "$API/api/nodes/$W2" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['node']['status'])" 2>/dev/null || echo "unknown")
    R3=$(curl -s "$API/api/nodes/$W3" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['node']['status'])" 2>/dev/null || echo "unknown")

    if [ "$R1" = "idle" ] && [ "$R2" = "idle" ] && [ "$R3" = "idle" ]; then
        echo ""
        echo "All workers finished!"

        # Read results from the filesystem
        A=$(cat "/tmp/armada-results/Apple-1/result" 2>/dev/null || echo "0")
        B=$(cat "/tmp/armada-results/Apple-2/result" 2>/dev/null || echo "0")
        C=$(cat "/tmp/armada-results/Apple-3/result" 2>/dev/null || echo "0")
        SUM=$((A + B + C))

        echo ""
        echo "  Apple-1: $A apples"
        echo "  Apple-2: $B apples"
        echo "  Apple-3: $C apples"
        echo "  ═══════════════════"
        echo "  I have $SUM apples"
        echo ""

        # Report the final result
        curl -s -X POST "$API/api/report" -H "Content-Type: application/json" \
            -d "{\"name\":\"Orchard\",\"status\":\"idle\",\"message\":\"I have $SUM apples\"}" > /dev/null

        # Kill workers
        curl -s -X DELETE "$API/api/nodes/$W1" > /dev/null
        curl -s -X DELETE "$API/api/nodes/$W2" > /dev/null
        curl -s -X DELETE "$API/api/nodes/$W3" > /dev/null

        echo "Workers killed. Demo complete."
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
echo "Dashboard still running: armada stop"
