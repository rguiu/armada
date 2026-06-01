#!/bin/bash
# Claude Code PostToolUse hook — reports "active" (Claude is processing result)
N="${ARMADA_NODE_NAME:-}"
[ -z "$N" ] && exit 0
TOOL_NAME=$(cat | python3 -c "import sys,json;print(json.load(sys.stdin).get('tool_name','unknown'))" 2>/dev/null || echo "unknown")
curl -s -X POST http://127.0.0.1:9100/api/report \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"$N\",\"status\":\"active\",\"message\":\"ran: $TOOL_NAME\"}" > /dev/null 2>&1
exit 0
