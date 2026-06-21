# Parallel Feature Build

Two agents build different parts of a feature independently, coordinating via messaging to agree on the interface contract.

## Pattern: Sibling Contract Exchange

```
Orchestrator
  ├── api-dev      writes the REST API
  └── frontend-dev writes the React component
        ↕ exchange API schema via send_message
```

## Why Parallel Agents?

A single agent would write the API, then the frontend sequentially. With two agents, both work simultaneously -- but they need to agree on the interface. The messaging system lets them exchange the contract without the orchestrator mediating every step.

## Expected Message Flow

```
1. Orchestrator spawns api-dev and frontend-dev
2. api-dev designs API schema, sends to frontend-dev via send_message
3. frontend-dev reads inbox, builds UI matching the schema
4. Both send "done" + results to orchestrator via send_message
5. Orchestrator collects via read_inbox, summarizes, kills workers
```

**Messages:** 3 (schema exchange + 2 completion notifications)

### Sequence Diagram

```mermaid
sequenceDiagram
    participant O as Orchestrator
    participant A as api-dev
    participant F as frontend-dev

    O->>A: spawn + send_task("design bookmark API")
    O->>F: spawn + send_task("wait for schema from api-dev")

    A->>A: designs REST API schema
    A->>F: send_message(schema JSON)
    A->>O: send_message(result: "API spec complete")

    F->>F: reads inbox, gets schema
    F->>F: builds React component
    F->>O: send_message(result: "component complete")

    O->>O: read_inbox → 2 results
    O->>A: kill_node
    O->>F: kill_node
```

## Prompt

Paste this into an orchestrator node:

```
Spawn two workers: "api-dev" and "frontend-dev".

api-dev should: design a REST API for a bookmark feature (create, list, delete
bookmarks). Define the request/response JSON schemas. Then send_message the
schema to frontend-dev (use get_tree to find its node ID). When done,
send_message to me (your parent, use get_my_info for parent_id) with
msg_type="result" and the final API spec.

frontend-dev should: wait for a message from api-dev (check read_inbox). Once
received, write a React component that calls the API using the schema provided.
When done, send_message to me with msg_type="result" and the component code.

Monitor both workers. Once both report results via messaging, summarize what
each produced and kill the workers.
```

## What Success Looks Like

- api-dev sends a schema message to frontend-dev
- frontend-dev's React component matches the API schema exactly
- Both completion messages arrive in the orchestrator's inbox
- Dashboard shows the full lifecycle: active -> messaging -> idle
