#!/bin/bash
# Claude Code PermissionRequest hook — reports "pending" with context
N="${ARMADA_NODE_NAME:-}"
[ -z "$N" ] && exit 0
INPUT=$(cat 2>/dev/null)
# Extract tool name, permission type, and first line of input for context
CTX=$(echo "$INPUT" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    tool = d.get('tool_name', 'unknown')
    perm = d.get('permission', '')
    inp = d.get('input', '')
    if isinstance(inp, dict):
        inp = inp.get('command', inp.get('text', str(inp)))
    inp_line = str(inp).split(chr(10))[0][:80] if inp else ''
    ctx = tool
    if perm: ctx += ' / ' + perm
    if inp_line: ctx += ' — ' + inp_line
    print(ctx)
except: print('waiting for approval')
" 2>/dev/null || echo "waiting for approval")
curl -s -X POST http://127.0.0.1:9100/api/report \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"$N\",\"status\":\"pending\",\"message\":\"$CTX\"}" > /dev/null 2>&1
exit 0
