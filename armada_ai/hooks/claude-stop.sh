#!/bin/bash
# Claude Code Stop hook — reports "idle" (Claude finished, waiting for user input)
N="${ARMADA_NODE_NAME:-}"
[ -z "$N" ] && exit 0
curl -s -X POST http://127.0.0.1:9100/api/report \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"$N\",\"status\":\"idle\",\"message\":\"waiting for input\"}" > /dev/null 2>&1
exit 0
