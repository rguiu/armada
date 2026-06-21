#!/bin/bash
# Claude Code PreToolUse hook — reports "active" (Claude is working)
N="${ARMADA_NODE_NAME:-}"
[ -z "$N" ] && exit 0
TOOL_NAME=$(cat | python3 -c "import sys,json;print(json.load(sys.stdin).get('tool_name','unknown'))" 2>/dev/null || echo "unknown")
armada report active "calling: $TOOL_NAME"
exit 0
