#!/bin/bash
# Claude Code PostToolUse hook — reports "active" (Claude is processing result)
N="${ARMADA_NODE_NAME:-}"
[ -z "$N" ] && exit 0
TOOL_NAME=$(cat | python3 -c "import sys,json;print(json.load(sys.stdin).get('tool_name','unknown'))" 2>/dev/null || echo "unknown")
armada report active "ran: $TOOL_NAME"
exit 0
