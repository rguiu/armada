# Multi-Project Security Audit

Multiple agents audit different codebases in parallel, each sending findings back to the orchestrator for a unified report.

## Pattern: Fan-Out + Collect

```
Orchestrator
  ├── audit-1  scans project A → sends findings
  ├── audit-2  scans project B → sends findings
  └── audit-3  scans project C → sends findings
        ↓
Orchestrator collects via read_inbox, compiles unified report
```

## Why Parallel Agents?

Auditing 3 codebases sequentially takes 3x the time. With parallel agents, all 3 run simultaneously. The orchestrator just waits for results in its inbox -- no polling required.

## Expected Message Flow

```
1. Orchestrator spawns 3 workers, sends each a scan task
2. Each worker scans its project directory
3. Each worker sends findings to orchestrator via send_message(msg_type="result")
4. Orchestrator reads inbox, compiles unified report, kills workers
```

**Messages:** 3 (one result per worker)

### Sequence Diagram

```mermaid
sequenceDiagram
    participant O as Orchestrator
    participant A1 as audit-1
    participant A2 as audit-2
    participant A3 as audit-3

    O->>A1: spawn + send_task("scan project-a")
    O->>A2: spawn + send_task("scan project-b")
    O->>A3: spawn + send_task("scan project-c")

    par Parallel Scanning
        A1->>A1: scans project-a
        A2->>A2: scans project-b
        A3->>A3: scans project-c
    end

    A1->>O: send_message(result: "3 issues found")
    A2->>O: send_message(result: "1 issue found")
    A3->>O: send_message(result: "5 issues found")

    O->>O: read_inbox → 3 results
    O->>O: compiles unified report (9 issues)
    O->>A1: kill_node
    O->>A2: kill_node
    O->>A3: kill_node
```

## Prompt

Paste this into an orchestrator node. Adjust the project paths to match your setup:

```
Spawn 3 workers: "audit-1", "audit-2", "audit-3".

Each worker should scan its assigned project directory for security issues:
- Hardcoded API keys, tokens, or passwords
- eval() or exec() usage
- SQL injection risks (string concatenation in queries)
- Missing input validation on API endpoints
- Sensitive data in logs

Summarize findings as a short report (max 10 issues, sorted by severity).
Then send_message the report to me (your parent, use get_my_info for parent_id)
with msg_type="result".

Assignments:
- audit-1: scan /path/to/project-a
- audit-2: scan /path/to/project-b
- audit-3: scan /path/to/project-c

Once all 3 workers have sent results (check read_inbox periodically), compile
a unified security report sorted by severity across all projects. Kill all
workers when done.
```

## What Success Looks Like

- All 3 workers scan their projects simultaneously
- Each sends a structured findings report to the orchestrator
- Orchestrator's inbox contains 3 result messages
- Final report aggregates issues across all projects by severity
- Workers killed after collection
