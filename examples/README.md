# Armada Messaging Examples

Practical examples demonstrating inter-node communication patterns for AI agent orchestration.

## Prerequisites

- Armada server running (`armada`)
- OpenCode or Claude Code installed
- A registered project (`armada projects add`)

## How to Run

1. Create an orchestrator node from the dashboard (http://127.0.0.1:9100) or CLI:
   ```bash
   armada create -p <project-id>
   ```
2. Attach to the node
3. Paste the prompt from the example
4. Watch the dashboard as workers spawn, exchange messages, and report back

## Examples

| Example | Pattern | What it demonstrates |
|---------|---------|---------------------|
| [Mesh Hello/ACK](messaging-test.md) | Sibling mesh | Full-mesh communication, ACK protocol, inbox draining |
| [Parallel Feature Build](parallel-feature-build.md) | Sibling contract exchange | Two agents agree on an interface via messaging, build independently |
| [Multi-Project Security Audit](multi-project-audit.md) | Fan-out + collect | Parallel analysis across repos, results collected via inbox |
| [Work Queue Task Board](work-queue-task-board.md) | Competing consumers | Dynamic task distribution, agents claim work from a shared queue |
| [Code Review Pipeline](code-review-pipeline.md) | Multi-round bidirectional | Iterative write/review cycle via messaging until approval |

## Messaging Patterns

### 1. Direct Messaging (point-to-point)
One node sends a message to another. Used for task assignment, result delivery, and feedback.
```
send_message(to_node_id=7, payload="review this code", msg_type="task")
```

### 2. Broadcast (fan-out)
Parent sends a message to all children. Used for announcements and coordination signals.
```
broadcast(payload="stop and report results")
```

### 3. Collect via Inbox
Parent reads completion messages from children. Replaces polling — workers notify when done.
```
read_inbox()  # returns all pending messages from children
```

### 4. Work Queue (competing consumers)
Tasks posted to a shared queue. Any idle agent can claim and execute. No parent-child relationship needed.
```
post_to_queue(payload="implement feature X")
claim_from_queue()
```

### 5. Notify Parent on Completion
Workers always send a result message to their parent when finished.
```
info = get_my_info()
send_message(to_node_id=info.parent_id, payload="job completed: ...", msg_type="result")
```

## Key MCP Tools

| Tool | Purpose |
|------|---------|
| `spawn_node(name)` | Spawn a child (inherits agent type and project) |
| `send_task(node_id, command)` | Send initial instructions to a node |
| `send_message(to_node_id, payload)` | Send a structured message |
| `read_inbox()` | Read pending messages |
| `ack_message(message_id)` | Mark a message as done |
| `broadcast(payload)` | Message all children |
| `post_to_queue(payload)` | Post to shared work queue |
| `claim_from_queue()` | Claim next available task |
| `get_my_info()` | Get own node ID, parent, project |
| `kill_node(node_id)` | Clean up when done |
