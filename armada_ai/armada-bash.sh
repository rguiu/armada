#!/bin/bash
# Armada Bash Node Wrapper
# Sourced by bash nodes in Armada tmux windows.
# Provides status reporting, child spawning, and inter-node communication.
#
# Available commands:
#   armada_report_active "msg"    — report node is working
#   armada_report_idle            — report node is done
#   armada_report_result "val"    — save result for parent to read
#   armada_spawn "name" [parent]  — spawn a child node, return its ID
#   armada_wait_child <id>        — poll child until idle, return its result
#   armada_kill_child <id>        — kill a child node

ARMADA_API="${ARMADA_API:-http://127.0.0.1:9100}"
ARMADA_NODE="${ARMADA_NODE_NAME:-unknown}"
ARMADA_RESULT_DIR="${ARMADA_RESULT_DIR:-/tmp/armada-results}"

mkdir -p "$ARMADA_RESULT_DIR/$ARMADA_NODE"

# ── Status Reporting ──

armada_report() {
    local status="$1" message="${2:-}"
    curl -s -X POST "$ARMADA_API/api/report" \
        -H "Content-Type: application/json" \
        -d "{\"name\":\"$ARMADA_NODE\",\"status\":\"$status\",\"message\":\"$message\"}" \
        > /dev/null 2>&1 || true
}

armada_report_active() {
    armada_report active "${1:-working}"
}

armada_report_idle() {
    armada_report idle ""
}

armada_report_error() {
    armada_report error "${1:-error}"
}

armada_report_result() {
    local result="$1"
    echo "$result" > "$ARMADA_RESULT_DIR/$ARMADA_NODE/result"
    armada_report idle "result: $result"
}

# ── Auto-report on command execution ──
# Trap DEBUG fires before every command — auto-reports active status
_armada_last_cmd=""
trap '_armada_cmd="$BASH_COMMAND"; if [ "$_armada_cmd" != "$_armada_last_cmd" ] && [[ ! "$_armada_cmd" =~ ^_armada_ ]] && [[ ! "$_armada_cmd" =~ ^armada_report ]]; then _armada_last_cmd="$_armada_cmd"; armada_report_active "$_armada_cmd" & fi' DEBUG

# ── Child Node Spawning ──

armada_spawn() {
    local child_name="${1:-}"
    local parent_id="${2:-}"

    if [ -z "$child_name" ]; then
        echo "Usage: armada_spawn <name> [parent_id]" >&2
        return 1
    fi

    if [ -z "$parent_id" ]; then
        # Find my own ID
        local my_id
        my_id=$(curl -s "$ARMADA_API/api/nodes" | python3 -c "
import sys, json
for n in json.load(sys.stdin):
    if n['name'] == '$ARMADA_NODE':
        print(n['id'])
        break
" 2>/dev/null)
        parent_id="$my_id"
    fi

    armada_report_active "spawning $child_name"

    local resp
    resp=$(curl -s -X POST "$ARMADA_API/api/nodes" \
        -H "Content-Type: application/json" \
        -d "{\"name\":\"$child_name\",\"parent_id\":$parent_id,\"agent_type\":\"bash\"}" 2>/dev/null)

    local child_id
    child_id=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)

    if [ -n "$child_id" ]; then
        echo "$child_id"
        return 0
    else
        armada_report_error "failed to spawn $child_name"
        return 1
    fi
}

# ── Wait for Child ──

armada_wait_child() {
    local child_id="$1"
    local timeout="${2:-120}"
    local poll=2
    local elapsed=0

    if [ -z "$child_id" ]; then
        echo "Usage: armada_wait_child <child_id> [timeout_seconds]" >&2
        return 1
    fi

    armada_report_active "waiting for child $child_id"

    while [ "$elapsed" -lt "$timeout" ]; do
        local status
        status=$(curl -s "$ARMADA_API/api/nodes/$child_id" 2>/dev/null | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d['node']['status'])
" 2>/dev/null)

        if [ "$status" = "idle" ] || [ "$status" = "dead" ] || [ "$status" = "error" ]; then
            # Try to read child's result
            local child_name
            child_name=$(curl -s "$ARMADA_API/api/nodes/$child_id" 2>/dev/null | python3 -c "
import sys, json
print(json.load(sys.stdin)['node']['name'])
" 2>/dev/null)

            local result
            result=$(cat "$ARMADA_RESULT_DIR/$child_name/result" 2>/dev/null || echo "")

            if [ -n "$result" ]; then
                echo "$result"
            fi
            return 0
        fi

        sleep "$poll"
        elapsed=$((elapsed + poll))
    done

    armada_report_error "timeout waiting for child $child_id"
    return 1
}

# ── Kill Child ──

armada_kill_child() {
    local child_id="$1"
    if [ -z "$child_id" ]; then
        echo "Usage: armada_kill_child <child_id>" >&2
        return 1
    fi
    curl -s -X DELETE "$ARMADA_API/api/nodes/$child_id" > /dev/null 2>&1
    armada_report_active "killed child $child_id"
}

echo "[armada] Node: $ARMADA_NODE — ready" >&2
