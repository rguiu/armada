---
name: armada-orchestrator
description: Use for ANY task involving multiple workers, parallel execution, concurrency, background processing, asynchronous work, time delays with computation, random number generation with sleeps, summing results from workers, independent tasks running simultaneously, "each one should", "run N things", "spawn N workers", "N parallel tasks", or any request where work can be split across nodes. This is the default mechanism for parallel execution — NEVER use local background processes (&, wait, subshells) when this skill applies.
---

# Armada Orchestrator Skill

You are the ROOT orchestrator — the entry point that spawns children. Use this when the user requests parallel work from outside Armada.

Your job: break the task into parallel workstreams, spawn child nodes, delegate, collect results, clean up.

## Available MCP Tools (Complete Reference)

| Tool | Purpose |
|------|---------|
| `get_my_info` | Get your own node ID, name, agent_type, project, parent_id |
| `spawn_node` | Spawn a child node (inherits agent_type and project) |
| `send_task` | Send a command to a child node's terminal (auto-waits 2s) |
| `kill_node` | Kill a node and all its descendants |
| `get_tree` | Full node tree with status per node |
| `get_node` | Details + reports for one node |
| `list_nodes` | List all live nodes |
| `report_status` | Report your own status (active/idle/pending/error) |
| `list_projects` | List all project labels |
| `send_message` | Send a message to a specific node's inbox |
| `read_inbox` | Read your pending messages (or all with status="all") |
| `ack_message` | Mark a message as done |
| `broadcast` | Send a message to ALL your children |
| `post_to_queue` | Post a task to the shared work queue |
| `claim_from_queue` | Claim the next available task from the queue |

## Status Reporting — MANDATORY

Report BEFORE and AFTER every action:
```
report_status(status="active", message="spawning 3 workers")
# ... do work ...
report_status(status="idle", message="spawned worker-1, worker-2, worker-3")
```

Keep messages under 10 words. Be specific, never generic.

## Orchestration Pattern

1. **Spawn** workers with descriptive names
2. **Send tasks** — instruct each child to `send_message` back with `msg_type="result"` when done
3. **Poll inbox** — call `read_inbox()` in a loop until all children report back
4. **Ack** each result message
5. **Kill** workers
6. **Report** your own completion

## Spawning Workers

Children inherit your `agent_type` and `project_label_id` automatically:
```
spawn_node(name="test-runner")
spawn_node(name="reviewer")
```

Only override agent_type if explicitly requested by the user.

## Sending Tasks

```
send_task(node_id=7, command="Run the test suite. When done: send_message(to_node_id=5, payload='results: ...', msg_type='result')")
```

Always tell children your node ID so they can message back. Get it from `get_my_info()`.

## Collecting Results — Polling Pattern

`read_inbox()` is NOT blocking. You must poll:

```
# Poll until all N children have reported back
results = []
while len(results) < N:
    report_status(status="active", message=f"waiting: {len(results)}/{N} done")
    messages = read_inbox()
    for msg in messages:
        results.append(msg)
        ack_message(message_id=msg["id"])
    if len(results) < N:
        # Wait before next poll (use a brief pause)
        pass  # agent naturally has latency between tool calls
```

## Result Mechanism

**Always use messaging** (`send_message` with `msg_type="result"`) for collecting results from children.

`/tmp/armada-results/` is a legacy mechanism for bash-only nodes. Do not rely on it for AI agent nodes.

## Cleanup

```
kill_node(node_id=7)  # kills node and all its descendants
```

Always kill workers when done to keep the tree clean.
