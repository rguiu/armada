#!/bin/bash
# Pre-populate Armada with demo data before recording.
# Run this first, then start recording the dashboard interactions.

set -euo pipefail
BASE="http://127.0.0.1:9100"

echo "Starting Armada..."
armada start
sleep 2

echo "Creating project..."
curl -s -X POST "$BASE/api/project-labels" -H 'Content-Type: application/json' \
  -d '{"id":"shipping-api","name":"Shipping API","path":"/tmp/armada-demo"}' > /dev/null

echo "Creating nodes..."
curl -s -X POST "$BASE/api/nodes" -H 'Content-Type: application/json' \
  -d '{"name":"Architect","project_label_id":"shipping-api","agent_type":"bash"}' > /dev/null
sleep 0.3
curl -s -X POST "$BASE/api/nodes" -H 'Content-Type: application/json' \
  -d '{"name":"Code-Reviewer","parent_id":1,"project_label_id":"shipping-api","agent_type":"bash"}' > /dev/null
sleep 0.3
curl -s -X POST "$BASE/api/nodes" -H 'Content-Type: application/json' \
  -d '{"name":"Test-Writer","parent_id":1,"project_label_id":"shipping-api","agent_type":"bash"}' > /dev/null

echo "Adding status reports..."
curl -s -X POST "$BASE/api/report" -H 'Content-Type: application/json' \
  -d '{"name":"Architect","status":"active","message":"analyzing API structure"}' > /dev/null
curl -s -X POST "$BASE/api/report" -H 'Content-Type: application/json' \
  -d '{"name":"Code-Reviewer","status":"active","message":"reviewing models.py"}' > /dev/null
curl -s -X POST "$BASE/api/report" -H 'Content-Type: application/json' \
  -d '{"name":"Test-Writer","status":"active","message":"writing integration tests"}' > /dev/null

echo ""
echo "Demo data ready. Dashboard: $BASE"
echo ""
echo "Recording checklist:"
echo "  1. Show the tree (expand/collapse)"
echo "  2. Click Architect → show detail panel with reports"
echo "  3. Click Attach on any node"
echo "  4. Kill Architect → show cascade (tree becomes empty)"
echo "  5. Show project labels section"
echo ""
