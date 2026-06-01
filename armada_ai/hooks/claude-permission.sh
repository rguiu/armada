#!/bin/bash
# Claude Code PermissionRequest hook — reports "pending" (waiting for user approval)
N="${ARMADA_NODE_NAME:-}"
[ -z "$N" ] && exit 0
TOOL_NAME=$(cat | python3 -c "import sys,json;print(json.load(sys.stdin).get('tool_name','unknown'))" 2>/dev/null || echo "unknown")
curl -s -X POST http://127.0.0.1:9100/api/report \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"$N\",\"status\":\"pending\",\"message\":\"permission: $TOOL_NAME\"}" > /dev/null 2>&1
exit 0
