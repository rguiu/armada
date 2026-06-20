---
name: armada-node
description: Use when ARMADA_NODE_NAME environment variable is set (running inside an Armada tmux window). Also use when the user wants to spawn parallel workers, delegate tasks concurrently, run multiple things at once, do background computation, split work across nodes, sum results from workers, or farm out tasks. This skill teaches mandatory per-step status reporting AND spawning/managing child nodes via MCP tools.
---

# Armada Node Skill

This skill equips an agent to act as a managed node in an Armada cluster. The agent reports its status on every turn and can spawn child nodes using MCP tools.

The agent discovers its node name from the `ARMADA_NODE_NAME` environment variable, which is set automatically when the tmux window is created.

## Installation

Armada automatically copies this skill to `.opencode/skills/` or `.claude/skills/` when a node is created. No manual steps needed.

## Prerequisites

The Armada server must be running at `http://127.0.0.1:9100`. Start it with:

```bash
armada start
```

---

## Available MCP Tools

All Armada operations are available as MCP tools. Use these instead of curl commands:

| Tool | Purpose |
|------|---------|
| `get_my_info` | Get your own node ID, name, agent_type, project |
| `spawn_node` | Spawn a child node (inherits agent_type and project automatically) |
| `send_task` | Send a command to a child node (auto-waits 2s for tmux init) |
| `kill_node` | Kill a node and all its descendants |
| `get_tree` | Get the full node tree with status |
| `get_node` | Get details for a specific node |
| `list_nodes` | List all live nodes |
| `report_status` | Report your own status (active, idle, pending, error) |
| `list_projects` | List all project labels |

## Status Reporting — MANDATORY

**You MUST report status BEFORE and AFTER every significant action.** This is not optional. Your activity log is the primary way the Armada dashboard monitors you. A silent node looks dead.

### Before every action (mark yourself active):

```
report_status(status="active", message="<what you are about to do>")
```

### After every action (mark yourself idle with results):

```
report_status(status="idle", message="<what you just did>")
```

### When waiting for user input (mark yourself pending):

The Armada pending plugin handles permission requests automatically — do NOT manually report `pending` for tool permission waits. Only report `pending` manually for non-permission waits: questions you ask the user, confirmations you need, or any prompt where you are waiting for a text response.

```
report_status(status="pending", message="<what you need from the user>")
```

This makes your node pulse yellow in the dashboard so the user knows you need attention.

### Report at EVERY step. Examples:

- `"spawning 3 workers"` then spawn them then `"spawned worker-1 (7), worker-2 (8), worker-3 (9)"`
- `"sending tasks to workers"` then send commands then `"tasks sent to all 3 workers"`
- `"polling workers: 0/3 done"` then poll then `"polling workers: 3/3 idle"`
- `"reading results"` then read then `"results: 5, 7, 9 -- sum=21"`
- `"cleaning up workers"` then kill then `"killed 3 workers, done"`

**Never use generic messages like "working" or "processing". Always say exactly what you are doing.**

Keep each message under 10 words but be specific.

## Getting Your Node Info

Use the `get_my_info` tool to discover your own ID, agent_type, project, and parent:

```
get_my_info()
# Returns: {"id": 5, "name": "my-node", "agent_type": "opencode", "project_label_id": "my-project", ...}
```

## Spawning Child Nodes

**RULE: Children ALWAYS inherit the parent's `agent_type`.** The `spawn_node` tool handles this automatically — you do NOT need to detect or pass agent_type. Only override if the user explicitly requests a different agent type.

```
spawn_node(name="worker-1")
spawn_node(name="worker-2")
spawn_node(name="reviewer", agent_type="bash")  # ONLY if user explicitly asks for bash
```

The tool automatically sets `parent_id` to your node and inherits your `project_label_id`.

## Sending Tasks to Workers

Use `send_task` to send commands to a worker's terminal. It automatically waits 2 seconds for tmux to initialize:

```
send_task(node_id=7, command="run the test suite and report results")
send_task(node_id=8, command="review the authentication module")
```

## Checking Workers

```
get_tree()            # full tree with status per node
get_node(node_id=7)   # details + reports for one node
```

## Killing Workers

```
kill_node(node_id=7)  # kills node and all its descendants
```

## Reading Child Results

Bash workers write results to `/tmp/armada-results/<name>/result`:
```bash
cat /tmp/armada-results/worker-1/result
```

## Complete Orchestration Example

To run 3 parallel workers using MCP tools:

```
# 1. Report what you're doing
report_status(status="active", message="spawning 3 workers")

# 2. Spawn 3 workers (agent_type and project inherited automatically)
w1 = spawn_node(name="apple-1")  # returns {"id": 7, ...}
w2 = spawn_node(name="apple-2")  # returns {"id": 8, ...}
w3 = spawn_node(name="apple-3")  # returns {"id": 9, ...}

report_status(status="active", message="spawned 3 workers, sending tasks")

# 3. Send tasks (auto-waits 2s before sending)
send_task(node_id=7, command="pick a random number and report it")
send_task(node_id=8, command="pick a random number and report it")
send_task(node_id=9, command="pick a random number and report it")

report_status(status="active", message="tasks sent, polling workers")

# 4. Poll until all workers are idle
# Use get_tree() or get_node() to check status periodically

# 5. Read results
# cat /tmp/armada-results/apple-1/result etc.

# 6. Clean up
kill_node(node_id=7)
kill_node(node_id=8)
kill_node(node_id=9)

report_status(status="idle", message="done, total = 42")
```

## Messaging

Nodes can send structured messages to each other using the task mailbox MCP tools. Messages are delivered automatically via tmux when the recipient is idle.

| Tool | Purpose |
|------|---------|
| `send_message(to_node_id, payload, msg_type?)` | Send a message to another node's inbox |
| `read_inbox(status?)` | Read your pending messages |
| `ack_message(message_id)` | Mark a message as done |
| `broadcast(payload, msg_type?)` | Send a message to all your children |
| `post_to_queue(payload, msg_type?)` | Post a task to the shared work queue |
| `claim_from_queue()` | Claim the next available task from the queue |

### Sending messages

```
send_message(to_node_id=5, payload="review the auth module", msg_type="task")
```

### Reading your inbox

```
read_inbox()                    # pending messages only
read_inbox(status="all")        # all messages
```

### Acknowledging messages

After processing a message, mark it done:
```
ack_message(message_id=42)
```

### Work queue

Post tasks that any idle agent can pick up:
```
post_to_queue(payload="run integration tests")
claim_from_queue()  # claims the next available task
```

## Guidelines

- Always spawn workers through the `spawn_node` MCP tool
- Workers auto-load armada skills and start reporting immediately
- Check the dashboard (http://127.0.0.1:9100) to visualize your tree
- Keep the tree clean — kill workers when they finish
- Workers inherit the project label automatically
