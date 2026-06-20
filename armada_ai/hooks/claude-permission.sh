#!/bin/bash
N="${ARMADA_NODE_NAME:-}"
[ -z "$N" ] && exit 0

INPUT=$(cat 2>/dev/null)

PARSED=$(echo "$INPUT" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    tool = d.get('tool_name', 'unknown')
    inp = d.get('tool_input', d.get('input', ''))
    if isinstance(inp, dict):
        inp = inp.get('command', inp.get('file_path', inp.get('text', str(inp))))
    inp_line = str(inp).split(chr(10))[0][:80] if inp else ''
    msg = tool
    if inp_line: msg += ' — ' + inp_line

    suggestions = d.get('permission_suggestions', [])
    if suggestions:
        options = [
            {'label': 'Allow once', 'key': '\n'},
            {'label': 'Always allow', 'key': '\x1b[B\n'},
            {'label': 'Deny', 'key': '\x1b[B\x1b[B\n'},
        ]
    else:
        options = [
            {'label': 'Allow', 'key': '\n'},
            {'label': 'Deny', 'key': '\x1b[B\n'},
        ]

    print(msg)
    print(json.dumps(options))
except:
    print('waiting for approval')
    print('[]')
" 2>/dev/null)

MSG=$(echo "$PARSED" | head -1)
OPTIONS=$(echo "$PARSED" | tail -1)

armada report pending "$MSG" --options "$OPTIONS"
exit 0
