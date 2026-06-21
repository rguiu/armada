#!/bin/bash
# Claude Code Stop hook — reports "idle" (Claude finished, waiting for user input)
N="${ARMADA_NODE_NAME:-}"
[ -z "$N" ] && exit 0
armada report idle "waiting for input"
exit 0
