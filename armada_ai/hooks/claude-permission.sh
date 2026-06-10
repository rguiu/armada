#!/bin/bash
# Claude Code PermissionRequest hook — reports "pending" (waiting for user approval)
N="${ARMADA_NODE_NAME:-}"
[ -z "$N" ] && exit 0
INPUT=$(cat 2>/dev/null)
TOOL_NAME=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_name', d.get('permission','unknown')))" 2>/dev/null || echo "unknown")
curl -s -X POST http://127.0.0.1:9100/api/report \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"$N\",\"status\":\"pending\",\"message\":\"Permission required: $TOOL_NAME\"}" > /dev/null 2>&1
exit 0
