#!/bin/bash
N="${ARMADA_NODE_NAME:-}"
[ -z "$N" ] && exit 0

INPUT=$(cat 2>/dev/null)
echo "=== $(date) ===" >> /tmp/armada-perm-debug.log 2>/dev/null
echo "$INPUT" >> /tmp/armada-perm-debug.log 2>/dev/null

BODY=$(echo "$INPUT" | python3 -c "
import sys, json, traceback
try:
    d = json.load(sys.stdin)
    
    # Dump all top-level keys to debug log
    with open('/tmp/armada-perm-debug.log', 'a') as log:
        log.write('KEYS: ' + str(list(d.keys())) + '\n')
        log.write('FULL: ' + json.dumps({k: str(v)[:100] for k, v in d.items()}, indent=2) + '\n')
    
    # Try every possible field that might contain the question text
    question = ''
    for field in ('prompt', 'question', 'message', 'text', 'reason', 'description', 'explanation', 'content', 'body'):
        val = d.get(field, '')
        if val and isinstance(val, str) and len(val) > len(question):
            question = val
        elif isinstance(val, dict) and 'text' in val:
            if len(str(val.get('text',''))) > len(question):
                question = str(val.get('text',''))
    
    if not question:
        inp = d.get('input', '')
        if isinstance(inp, dict):
            for k in ('command', 'text', 'content'):
                if inp.get(k) and len(str(inp[k])) > len(question):
                    question = str(inp[k])
        elif inp:
            question = str(inp)
    
    question = question.strip()[:300]
    tool = d.get('tool_name', '')
    
    msg = question if question else (tool or 'waiting for approval')
    
    options = d.get('options', [])
    if not options:
        options = []
    
    print(json.dumps({'name': '$N', 'status': 'pending', 'message': msg, 'options': options}))
except Exception as e:
    with open('/tmp/armada-perm-debug.log', 'a') as log:
        traceback.print_exc(file=log)
    print(json.dumps({'name': '$N', 'status': 'pending', 'message': 'waiting for approval', 'options': []}))
")

curl -s -X POST http://127.0.0.1:9100/api/report \
  -H "Content-Type: application/json" \
  -d "$BODY" > /dev/null 2>&1
exit 0
