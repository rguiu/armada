# Armada — Task Cost Tracking Plan

## The Problem

You run agents to do work. Each piece of work costs money (API tokens). Currently Armada tracks cost **per node** — you see how much each agent has spent total. But you don't know:

- "How much did fixing that bug cost?"
- "What was the AI cost for this PR?"
- "This Jira ticket took $3.42 in AI time"

The cost is there, it's just not connected to the **work product**.

## Core Concept: Tasks

A **task** is a unit of work assigned to a node. It has a start time, an end time, and accumulates cost while active. When the task is closed, the cost is frozen and becomes a reportable line item.

```
Task: "Fix login timeout"        Task: "Write tests for auth"
├── Node: code-reviewer-001      ├── Node: code-reviewer-001
├── Started: 10:30               ├── Started: 11:45
├── Closed:  10:52               ├── Closed:  12:05
├── Cost:    $0.42               ├── Cost:    $0.18
├── Tokens:  12K in / 8K out     ├── Tokens:  5K in / 3K out
└── Status:  done                └── Status:  done

     Total for code-reviewer-001 this session: $0.60
```

## Task Lifecycle

```
1. CREATE    — "start a new task for this node"
   POST /api/nodes/:id/tasks { "description": "Fix login timeout" }

2. ACTIVE    — node keeps working. Cost accumulates via normal /api/report calls.
   The task_id is attached to each report.

3. CLOSE     — "this task is done"
   POST /api/tasks/:id/close
   Cost is frozen. No more cost allocated to this task.

4. COMPLETE  — (optional) task can be re-opened to add more cost
   POST /api/tasks/:id/reopen

A node can work on MULTIPLE tasks sequentially (task A, then task B).
A node works on ONE task at a time (the active task).
Cost between tasks accrues to the node itself (untracked overhead).
```

## Where Tasks Come From

### 1. Manual — via the dashboard
A text input in the detail panel: "What are you working on?" → creates a task. Agent works → agent finishes → user clicks "Done" → cost frozen.

### 2. Via `/send` — orchestrator assigns work
```
POST /api/nodes/:id/send
{
  "command": "review this PR",
  "task": {
    "description": "Review PR #42",
    "ref": "PR-42"           // optional external reference
  }
}
```
The `/send` call creates a task, sends the command, cost accumulates.

### 3. Via agent self-report — agent claims a task
Agents already report status. They could also report task boundaries:
```
curl -X POST /api/report
-d '{"name": "architect", "status": "active",
     "task": {"action": "start", "description": "Refactoring auth module"}}'

curl -X POST /api/report
-d '{"name": "architect", "status": "idle",
     "task": {"action": "close"}}'
```

### 4. Implicit — automatic task per /send
Every `/send` with a command auto-creates a task. When the node goes idle after that task, it auto-closes.

## Cost Attribution Flow

```
                    ┌─────────────────┐
                    │   Node running   │
                    │ cost: $0.00      │
                    └────────┬────────┘
                             │ POST /api/nodes/:id/tasks { desc: "Fix bug" }
                             ▼
              ┌──────────────────────────┐
              │   Task: "Fix bug"         │
              │   node_id: 5              │
              │   cost: $0.00 (so far)    │
              │   status: active          │
              └────────────┬─────────────┘
                           │ /api/report { node: "architect", cost: 0.15 }
                           ▼
              ┌──────────────────────────┐
              │   Task: "Fix bug"         │
              │   cost: $0.15             │  ← cost added to task
              │   Node cost: $0.15        │  ← also tracked on node
              └────────────┬─────────────┘
                           │ /api/report { node: "architect", cost: 0.10 }
                           ▼
              ┌──────────────────────────┐
              │   Task: "Fix bug"         │
              │   cost: $0.25             │
              └────────────┬─────────────┘
                           │ POST /api/tasks/:id/close
                           ▼
              ┌──────────────────────────┐
              │   Task: "Fix bug"         │
              │   cost: $0.25 (frozen)    │
              │   status: closed          │
              │   closed_at: 10:52        │
              └──────────────────────────┘
```

Node total cost = sum of all task costs + untracked overhead between tasks.

## Data Model

```sql
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id INTEGER NOT NULL REFERENCES nodes(id),
    description TEXT NOT NULL,
    ref TEXT,                    -- optional: Jira ID, PR number, commit hash
    status TEXT DEFAULT 'active', -- active, closed
    cost REAL DEFAULT 0.0,
    tokens_in INTEGER DEFAULT 0,
    tokens_out INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    closed_at TEXT
);
```

## API

```
# Tasks
POST   /api/nodes/:id/tasks          { "description": "...", "ref": "JIRA-123" }
GET    /api/nodes/:id/tasks          list tasks for this node
GET    /api/nodes/:id/tasks/active   get currently active task (or null)
POST   /api/tasks/:id/close          close task, freeze cost
POST   /api/tasks/:id/reopen         reopen a closed task

# Reports (updated)
GET    /api/tasks/:id/reports        cost reports scoped to this task
GET    /api/tasks                    all tasks across all nodes
GET    /api/tasks?ref=JIRA-123       find tasks by external reference
```

## Output: How Cost Gets to Jira, PR, or Commit

### Option A: Manual copy
Dashboard shows tasks with costs. User copies the cost summary and pastes into Jira comment / PR description.

### Option B: Webhook on task close
When a task closes, POST to a configurable URL:
```json
{
  "task_id": 42,
  "description": "Fix login timeout",
  "ref": "JIRA-123",
  "cost": 0.42,
  "tokens_in": 12000,
  "tokens_out": 8000,
  "node": "code-reviewer-001",
  "duration": "22m"
}
```
Could post to:
- Jira webhook (add comment with cost)
- GitHub PR (add comment)
- Slack channel
- Custom endpoint

### Option C: Export / summary command
```bash
armada tasks summary              # this session: 5 tasks, $2.34 total
armada tasks export --csv         # CSV for spreadsheet
armada tasks summary --ref JIRA-123  # filter by reference
```

### Option D: Commit message convention
Agent commits with a trailer:
```
feat: add login timeout handling

Armada-task: Fix login timeout
Armada-cost: $0.42
Armada-tokens: 12K/8K
```
A post-commit hook could parse these and aggregate. Feels fragile — commits are immutable, costs might not be final at commit time.

## Recommended Path

| Phase | What | Why first |
|-------|------|-----------|
| **1** | Task CRUD: create, list, close, reopen. Cost auto-attributed via existing `/api/report` | Foundation |
| **2** | Dashboard UI: task input in detail panel, task history, active task badge | Usable day 1 |
| **3** | Auto-task on `/send`: every command creates a task, auto-closes on idle | Zero-friction |
| **4** | Webhooks on task close: configurable URL, JSON payload | Integrations |
| **5** | `armada tasks` CLI: summary, list, export | Reporting |

**Skip for now:** commit message embedding. Too fragile, cost is often not known at commit time. Better to attach cost AFTER the fact via the webhook.

## Dashboard UI Sketch

```
Detail panel for "code-reviewer-001"
┌─────────────────────────────────────────────┐
│ ● code-reviewer-001          ACTIVE         │
│ Agent: claude | Project: shipping-api       │
│ Cost: $1.23 total                           │
│                                             │
│ ┌─ Current Task ──────────────────────────┐ │
│ │ Fix login timeout            $0.42       │ │
│ │ Started 10:30 · 22m ago                  │ │
│ │ [Mark Done]                              │ │
│ └─────────────────────────────────────────┘ │
│                                             │
│ ┌─ Past Tasks ────────────────────────────┐ │
│ │ Refactor models     $0.81   10:05-10:28 │ │
│ │ Add health check    $0.00   09:50-10:02 │ │
│ └─────────────────────────────────────────┘ │
│                                             │
│ [+ New task: _____________________] [Start] │
└─────────────────────────────────────────────┘
```
