#!/bin/bash
# Armada Demo Script
# Record with Kap (https://getkap.co) for a clean GIF

set -euo pipefail

CMD="armada"
BASE="http://127.0.0.1:9100"
COLS=80

header() {
  echo ""
  printf '%*s\n' "$COLS" '' | tr ' ' '─'
  echo "  $1"
  printf '%*s\n' "$COLS" '' | tr ' ' '─'
  echo ""
  sleep 1
}

step() {
  echo "▶ $1"
  sleep 0.8
}

# ──────────────────────────────────────────────────
header "A R M A D A  —  Agent Orchestration Demo"
step "Starting server..."
$CMD start 2>/dev/null || python3 -c "from armada_ai.server import start_server; start_server(daemon=True, open_browser=False)"
sleep 2
echo "  ✓ Server running at $ARMADA"

# ── Register projects ──
header "1. Registering Projects"
step "Adding 'shipping-api' project..."
curl -s -X POST "$ARMADA/api/project-labels" \
  -H "Content-Type: application/json" \
  -d '{"id":"shipping-api","name":"Shipping API","path":"/tmp/armada-demo"}'
echo ""
echo "  ✓ shipping-api registered"

step "Adding 'payment-service' project..."
curl -s -X POST "$ARMADA/api/project-labels" \
  -H "Content-Type: application/json" \
  -d '{"id":"payment","name":"Payment Service","path":"/tmp/armada-demo"}'
echo ""
echo "  ✓ payment-service registered"

step "Listing all projects..."
curl -s "$ARMADA/api/project-labels" | python3 -c "
import sys,json
for p in json.load(sys.stdin):
    print(f'  • {p[\"name\"]} ({p[\"id\"]}) → {p[\"path\"]}')
"

# ── Create orchestration tree ──
header "2. Building the Agent Tree"
step "Creating root orchestrator node: 'Architect'..."
curl -s -X POST "$ARMADA/api/nodes" \
  -H "Content-Type: application/json" \
  -d '{"name":"Architect","project_label_id":"shipping-api","agent_type":"opencode"}'
echo ""
echo "  ✓ Architect (id=1, orchestrator, #EF4444)"

sleep 0.5

step "Spawning child worker: 'Code-Reviewer'..."
curl -s -X POST "$ARMADA/api/nodes" \
  -H "Content-Type: application/json" \
  -d '{"parent_id":1,"project_label_id":"shipping-api","agent_type":"opencode"}'
echo ""
echo "  ✓ Code-Reviewer (id=2, child of Architect, #F97316)"

sleep 0.3

step "Spawning child worker: 'Test-Writer'..."
curl -s -X POST "$ARMADA/api/nodes" \
  -H "Content-Type: application/json" \
  -d '{"parent_id":1,"project_label_id":"shipping-api","agent_type":"opencode"}'
echo ""
echo "  ✓ Test-Writer (id=3, child of Architect, #EAB308)"

sleep 0.3

step "Spawning grandchild worker: 'Unit-Tests'..."
curl -s -X POST "$ARMADA/api/nodes" \
  -H "Content-Type: application/json" \
  -d '{"parent_id":3,"project_label_id":"shipping-api","agent_type":"opencode"}'
echo ""
echo "  ✓ Unit-Tests (id=4, child of Test-Writer, #22C55E)"

# ── Simulate agent activity ──
header "3. Agent Status Reports"

step "Agents report activity via curl hooks..."
curl -s -X POST "$ARMADA/api/report" \
  -H "Content-Type: application/json" \
  -d '{"name":"Architect","status":"active","message":"analyzing API structure"}' > /dev/null
echo "  • Architect → active: 'analyzing API structure'"

curl -s -X POST "$ARMADA/api/report" \
  -H "Content-Type: application/json" \
  -d '{"name":"Code-Reviewer","status":"active","message":"reviewing models.py"}' > /dev/null
echo "  • Code-Reviewer → active: 'reviewing models.py'"

curl -s -X POST "$ARMADA/api/report" \
  -H "Content-Type: application/json" \
  -d '{"name":"Test-Writer","status":"active","message":"writing integration tests"}' > /dev/null
echo "  • Test-Writer → active: 'writing integration tests'"

curl -s -X POST "$ARMADA/api/report" \
  -H "Content-Type: application/json" \
  -d '{"name":"Unit-Tests","status":"active","message":"testing auth module"}' > /dev/null
echo "  • Unit-Tests → active: 'testing auth module'"

sleep 1

step "Agents finishing work..."
curl -s -X POST "$ARMADA/api/report" \
  -H "Content-Type: application/json" \
  -d '{"name":"Code-Reviewer","status":"idle","message":""}' > /dev/null
curl -s -X POST "$ARMADA/api/report" \
  -H "Content-Type: application/json" \
  -d '{"name":"Test-Writer","status":"idle","message":""}' > /dev/null
echo "  • Code-Reviewer, Test-Writer → idle (finished)"

# ── Show tree ──
header "4. Dashboard Tree View"
step "GET /api/tree — full hierarchy with live status..."
curl -s "$ARMADA/api/tree" | python3 -c "
import sys, json
def show(nodes, indent=0):
    for n in nodes:
        icon = '●' if n['status'] == 'active' else '○'
        msg = n.get('latest_message','') or ''
        print('  ' * indent + f'{icon} {n[\"name\"]} [{n[\"status\"]}] — {msg}')
        if n.get('children'):
            show(n['children'], indent + 1)
show(json.load(sys.stdin))
"

# ── Node detail ──
header "5. Node Detail View"
step "GET /api/nodes/1 — Architect's full activity log..."
curl -s "$ARMADA/api/nodes/1" | python3 -c "
import sys, json
data = json.load(sys.stdin)
n = data['node']
print(f'  Node: {n[\"name\"]}')
print(f'  Status: {n[\"status\"]}')
print(f'  Color: {n[\"colour\"]}')
print(f'  Project: {n[\"project_label_name\"]}')
print(f'  Children: {len(data[\"children\"])} direct, 1 grandchild')
print(f'')
print(f'  Recent reports:')
for r in data['reports'][:4]:
    print(f'    [{r[\"timestamp\"]}] {r[\"status\"]:>6}  {r.get(\"message\",\"\")}')
"

# ── Cascade kill ──
header "6. Cascade Kill"
step "Killing Architect (root) — cascades to all children..."
curl -s -X DELETE "$ARMADA/api/nodes/1" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f'  Killed {data[\"killed\"]} agents (Architect + 3 workers)')
"

step "Verifying tree is empty..."
result=$(curl -s "$ARMADA/api/tree")
if [ "$result" = "[]" ]; then
  echo "  ✓ Clean tree — all agents removed"
else
  echo "  $result"
fi

# ── Done ──
header "D E M O   C O M P L E T E"
echo ""
echo "  Dashboard:  $ARMADA"
echo "  API:        $ARMADA/api/tree"
echo "  Skills:     skills/armada-*.md"
echo ""
  echo "  Stop server: $CMD stop"
echo ""
