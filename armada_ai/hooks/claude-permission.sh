#!/bin/bash
# Claude Code PermissionRequest hook — reports "pending" with question and options
N="${ARMADA_NODE_NAME:-}"
[ -z "$N" ] && exit 0
INPUT=$(cat 2>/dev/null)
# Debug: dump raw input so we can see what Claude sends
echo "$INPUT" >> /tmp/armada-claude-permission.log 2>/dev/null
DATA=$(echo "$INPUT" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    tool = d.get('tool_name', '')
    perm = d.get('permission', '')
    inp = d.get('input', '')
    if isinstance(inp, dict):
        inp = inp.get('command', inp.get('text', str(inp)))
    
    parts = []
    if tool: parts.append(tool)
    if perm: parts.append(perm)
    
    desc = d.get('prompt') or d.get('question') or d.get('reason') or d.get('text') or d.get('description') or ''
    if desc:
        parts.append(desc[:120])
    elif inp:
        parts.append(str(inp)[:120])
    
    ctx = ' — '.join(parts) if parts else 'waiting for approval'
    
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
