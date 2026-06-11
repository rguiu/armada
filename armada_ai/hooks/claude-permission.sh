#!/bin/bash
# Claude Code PermissionRequest hook — reports "pending" with question and options
N="${ARMADA_NODE_NAME:-}"
[ -z "$N" ] && exit 0
INPUT=$(cat 2>/dev/null)
# Extract context and available options from the permission request
DATA=$(echo "$INPUT" | python3 -c "
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
    
    options = d.get('options', [])
    if not options:
        options = [{'label': 'Allow once', 'key': chr(10)}, {'label': 'Allow always', 'key': chr(9)+chr(10)}, {'label': 'Deny', 'key': chr(9)+chr(9)+chr(10)}]
    
    print(json.dumps({'message': ctx, 'options': options}))
except:
    print(json.dumps({'message': 'waiting for approval', 'options': [{'label': 'Allow once', 'key': chr(10)}, {'label': 'Allow always', 'key': chr(9)+chr(10)}, {'label': 'Deny', 'key': chr(9)+chr(9)+chr(10)}]}))
" 2>/dev/null || echo '{"message":"waiting for approval","options":[{"label":"Allow once","key":"\n"},{"label":"Allow always","key":"\t\n"},{"label":"Deny","key":"\t\t\n"}]}')

MSG=$(echo "$DATA" | python3 -c "import sys,json; print(json.load(sys.stdin)['message'])" 2>/dev/null)
OPTS=$(echo "$DATA" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin)['options']))" 2>/dev/null)

curl -s -X POST http://127.0.0.1:9100/api/report \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"$N\",\"status\":\"pending\",\"message\":\"$MSG\",\"options\":$OPTS}" > /dev/null 2>&1
exit 0
