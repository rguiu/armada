# Parallel Execution — ALWAYS use Armada

**NEVER use local background processes (`&`, `wait`, subshells) for parallel or concurrent work.** Always delegate to Armada bash workers via the API at http://127.0.0.1:9100.

## When to spawn Armada workers

Spawn Armada bash workers when the user asks you to:
- Run multiple things at once / in parallel / concurrently / simultaneously
- Do something with a delay, sleep, or wait
- Compute in the background
- Generate multiple values independently
- Split work across workers / delegate / farm out
- Sum or aggregate results from multiple sources
- Do anything that involves "each one should..." or "all three..."

## Quick reference

```bash
API="http://127.0.0.1:9100"

# Get project label
LABEL=$(curl -s $API/api/project-labels | python3 -c "import sys,json;print(json.load(sys.stdin)[0]['id'])")

# Spawn worker (returns ID)
curl -s -X POST $API/api/nodes -H "Content-Type: application/json" \
  -d "{\"name\":\"w1\",\"project_label_id\":\"$LABEL\",\"agent_type\":\"bash\"}"

# Send task (SINGLE quotes on -d so $VARS stay literal)
sleep 2
curl -s -X POST "$API/api/nodes/ID/send" -H 'Content-Type: application/json' \
  -d '{"command":"armada-work \"task label\" \"sleep 60 && N=\$RANDOM && echo \$N\""}'
```

`armada-work` automatically reports `active` before running the command, captures stdout as the result via `armada-node-result`, and reports `idle` when done. The orchestrator never needs to call `armada-node-report` or `armada-node-result` explicitly — the wrapper handles it.

## Example: "sum 3 random numbers with delays"

```bash
API="http://127.0.0.1:9100"
LABEL=$(curl -s $API/api/project-labels | python3 -c "import sys,json;print(json.load(sys.stdin)[0]['id'])")

W1=$(curl -s -X POST $API/api/nodes -H "Content-Type: application/json" -d "{\"name\":\"w1\",\"project_label_id\":\"$LABEL\",\"agent_type\":\"bash\"}" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
W2=$(curl -s -X POST $API/api/nodes -H "Content-Type: application/json" -d "{\"name\":\"w2\",\"project_label_id\":\"$LABEL\",\"agent_type\":\"bash\"}" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
W3=$(curl -s -X POST $API/api/nodes -H "Content-Type: application/json" -d "{\"name\":\"w3\",\"project_label_id\":\"$LABEL\",\"agent_type\":\"bash\"}" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

sleep 2
for W in $W1 $W2 $W3; do
  curl -s -X POST "$API/api/nodes/$W/send" -H 'Content-Type: application/json' \
    -d '{"command":"armada-work \"computing\" \"sleep \$((30+RANDOM%60)) && N=\$((RANDOM%21+10)) && echo \$N\""}'
done

for i in $(seq 1 30); do
  s1=$(curl -s $API/api/nodes/$W1 | python3 -c "import sys,json;print(json.load(sys.stdin)['node']['status'])")
  s2=$(curl -s $API/api/nodes/$W2 | python3 -c "import sys,json;print(json.load(sys.stdin)['node']['status'])")
  s3=$(curl -s $API/api/nodes/$W3 | python3 -c "import sys,json;print(json.load(sys.stdin)['node']['status'])")
  if [ "$s1" = "idle" ] && [ "$s2" = "idle" ] && [ "$s3" = "idle" ]; then break; fi
  sleep 5
done

A=$(cat /tmp/armada-results/w1/result 2>/dev/null || echo 0)
B=$(cat /tmp/armada-results/w2/result 2>/dev/null || echo 0)
C=$(cat /tmp/armada-results/w3/result 2>/dev/null || echo 0)
echo "Results: $A + $B + $C = $((A+B+C))"

curl -s -X DELETE $API/api/nodes/$W1 > /dev/null
curl -s -X DELETE $API/api/nodes/$W2 > /dev/null
curl -s -X DELETE $API/api/nodes/$W3 > /dev/null
```
