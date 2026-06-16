#!/bin/bash
# Armada Demo — record with Kap (browser window)
# Usage: bash demo-run.sh
set -euo pipefail

DEMO_DB="$HOME/.armada/armada-demo.db"
BASE="http://127.0.0.1:9100"

echo "=== Cleaning up ==="
armada stop 2>/dev/null || true
sleep 1

echo "=== Seeding demo DB (armada, vllm, sglang, nano-vllm, pglease) ==="
ARMADA_DB_PATH="$DEMO_DB" armada demodb seed

echo "=== Starting Armada ==="
ARMADA_DB_PATH="$DEMO_DB" armada start &
PID=$!
for i in $(seq 1 15); do
  curl -s "$BASE/api/tree" >/dev/null 2>&1 && break
  sleep 1
done
echo "  Ready: $BASE"

echo "=== Creating demo agents (armada project) ==="

# Architect: root orchestrator
curl -sf -X POST "$BASE/api/nodes" -H "Content-Type: application/json" \
  -d '{"name":"Architect","project_label_id":"armada","agent_type":"bash"}' >/dev/null
sleep 0.5
curl -sf -X POST "$BASE/api/report" -H "Content-Type: application/json" \
  -d '{"name":"Architect","status":"active","message":"designing WebSocket tree update protocol to replace 10s polling"}' >/dev/null

# Code-Reviewer: child of Architect
curl -sf -X POST "$BASE/api/nodes" -H "Content-Type: application/json" \
  -d '{"name":"Code-Reviewer","parent_id":1,"project_label_id":"armada","agent_type":"bash"}' >/dev/null
sleep 0.3
curl -sf -X POST "$BASE/api/report" -H "Content-Type: application/json" \
  -d '{"name":"Code-Reviewer","status":"active","message":"auditing remaining innerHTML paths for XSS after SESSION_LOG fixes"}' >/dev/null

# Test-Runner: child of Architect
curl -sf -X POST "$BASE/api/nodes" -H "Content-Type: application/json" \
  -d '{"name":"Test-Runner","parent_id":1,"project_label_id":"armada","agent_type":"bash"}' >/dev/null
sleep 0.3
curl -sf -X POST "$BASE/api/report" -H "Content-Type: application/json" \
  -d '{"name":"Test-Runner","status":"active","message":"running integration suite against split-attach with 3 tmux sessions"}' >/dev/null

echo ""
echo "═══════════════════════════════════════════════"
echo "  DEMO READY — $BASE"
echo "═══════════════════════════════════════════════"
echo ""
echo "Pre-existing: 3 agents on armada project"
echo "  Architect    → WebSocket tree update protocol"
echo "  Code-Reviewer→ XSS audit (SESSION_LOG follow-up)"
echo "  Test-Runner  → split-attach integration tests"
echo ""
echo "Projects seeded: armada, vllm, sglang, nano-vllm, pglease"
echo ""

cat <<'FLOW'
╔══════════════════════════════════════════════════════════════╗
║                   RECORDING FLOW (2-3 min)                   ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  1. SHOW TREE (30s)                                         ║
║     Expand/collapse, show status colors, project sidebar     ║
║                                                              ║
║  2. SHOW DETAILS (30s)                                      ║
║     Click Architect → detail panel, status report history    ║
║     Click Code-Reviewer → show its report                    ║
║                                                              ║
║  3. CREATE AGENTS (60s)                                     ║
║     +Node → "Streaming-Output" | nano-vLLM                  ║
║       Prompt: "Add streaming token output param to          ║
║                LLM.generate() in nanovllm/llm.py"            ║
║                                                              ║
║     +Node → "JsonSchema" | SGLang                            ║
║       Prompt: "Add response_format json_schema support      ║
║                to the OpenAI-compatible endpoint"            ║
║                                                              ║
║     +Node → "Prometheus-Metrics" | PGLease                   ║
║       Prompt: "Add Prometheus metrics endpoint exposing     ║
║                lease acquisition latency and active count"   ║
║                                                              ║
║  4. CASCADE KILL (20s)                                      ║
║     Click Architect → Kill → whole subtree vanishes         ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝

Suggested real issues for each project:
  nano-vLLM → streaming token output (no OpenAI server exists yet)
  SGLang    → json_schema response_format (common LLM serving gap)
  vLLM      → token usage headers on streaming responses
  PGLease   → Prometheus metrics (missing observability layer)
  Armada    → (used for pre-existing demo agents above)

Export from Kap as WebM. Add to README:
  <video src="demo.webm" autoplay loop muted playsinline
         width="100%"></video>

Stop server:  armada stop
FLOW

wait "$PID" 2>/dev/null || true
