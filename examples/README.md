# Armada Messaging Examples

Practical examples demonstrating inter-node communication patterns for AI agent orchestration. Each example has been executed and verified.

## How to Run

<!-- TODO: fill in with CLI-based workflow -->

## Examples

| Example | Pattern | Result |
|---------|---------|--------|
| [Mesh Hello/ACK](mesh-hello-ack/) | Sibling mesh | PASS — 12 messages, all ACKed |
| [Parallel Feature Build](parallel-feature-build/) | Sibling contract exchange | PASS — API spec + React component |
| [Multi-Project Security Audit](multi-project-audit/) | Fan-out + collect | PASS — 3 projects, 16 issues found |
| [Work Queue Task Board](work-queue-task-board/) | Competing consumers | PASS — 5 tasks, dynamic distribution |
| [Code Review Pipeline](code-review-pipeline/) | Multi-round bidirectional | PASS — LRU cache approved round 2 |

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
read_inbox()
```

### 4. Work Queue (competing consumers)
Tasks posted to a shared queue. Any idle agent can claim and execute.
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
