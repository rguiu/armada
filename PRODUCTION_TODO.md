# Armada — Production Readiness TODO

> Generated 2025-06-08 from existing PLAN.md, STRATEGY.md + competitive audit.
> Mark `[x]` when done, `[ ]` when pending, `[/]` when in progress.

## 🔴 Security (Showstopper — must fix before sharing)

- [x] **Move token out of URL** — `Authorization: Bearer` header or cookie. Token in URL leaks via browser history, screenshots, QR photos. (~1h)
- [x] **Add CSP header** — Content-Security-Policy to block injected scripts from agent output. (~15min)
- [x] **Separate tmux session per agent** — currently all agents share one tmux session. Agent in one window can access all others. (~1 day)
- [x] **Vendor xterm.js locally** — remove jsdelivr/esm.sh CDN dependency. Compromised CDN = compromised dashboard. (~1 day)
- [x] **Clear sensitive env vars** — agents inherit `~/.ssh`, `~/.aws`, all shell vars. Sanitize before spawn. (~1h)
- [x] **Audit xterm.js `innerHTML`** — agent output could inject HTML/JS. Switch to `textContent`. (~1h)

## 🟠 Reliability (Can't trust it without these)

- [x] **Fix SQLite concurrency** — "database is locked" with 8+ nodes. Single connection + serialized writes. (~2h)
- [x] **Server restart recovery** — server crash → agents survive in tmux but server can't reconnect. Auto-reconnect on restart. (~2 days)
- [x] **Agent auto-restart on crash** — dead tmux pane → restart with same config + resume prompt. (~1 day)
- [x] **Error page** — show "reconnecting..." instead of blank white when server restarts. (~1h)
- [x] **Structured agent logs** — JSONL per agent, searchable. Currently everything is in tmux scrollback. (~1 day)
- [x] **Persistent artifacts per agent** — mount `./armada/artifacts/<node>/` so agent output survives pane death. (~2h)

## 🟡 Observability (Can't debug without these)

- [x] **`/health` endpoint** — `{"status":"ok","agents":5,"uptime":3600}`. Unlocks Docker, K8s, monitoring. (~30min)
- [x] **Prometheus `/metrics` endpoint** — agent_count, tasks_total, task_duration_seconds, errors_total. (~2h)
- [x] **Structured logging** — log levels (DEBUG/INFO/WARN/ERROR), JSON format, log rotation. (~2h)
- [ ] **Per-agent cost tracking** — token usage, API spend. Already in schema but needs UI. (~1 day)

## 🟢 Platform (More users = more feedback)

- [x] **`pip install armada`** — publish to PyPI. Already have pyproject.toml, add `[project.scripts]`. (~2h)
- [ ] **Linux support** — fix `lsof`, iTerm AppleScript, `fuser` platform-specific calls. (~2 days)
- [ ] **Dockerfile** — `FROM python:3.12-slim`, install tmux, expose 9100. (~1h)
- [x] **systemd/launchd service** — survive reboot. `armada service install`. (~2h)
- [x] **PWA manifest + service worker** — install to phone home screen, push notifications, offline cache. (~1 day)
- [x] **Config file** — `~/.armada/config.yaml` for declarative setup (projects, default agent type, port). (~2h)

## 🔵 UX Polish (First impressions)

- [ ] **WebSocket push for dashboard** — replace 10s polling with real-time updates. (~1 day)
- [ ] **Dark/light theme toggle** — already dark, add light mode. (~2h)
- [x] **Loading states** — spinner/skeleton while tree loads, instead of blank pane. (~1h)
- [x] **Keyboard shortcuts** — `Cmd+K` command bar, `r` refresh, `n` new node. (~2h)
- [x] **Empty states** — "No agents yet. Create your first node →" instead of empty tree. (~1h)

## ⚪ Future (v2+)

- [ ] **Multi-server federation** — one dashboard → agents across multiple machines
- [ ] **Plugin system** — community extensions for agent types, status extractors, skill providers
- [ ] **Unified skill format** — one skill file → works in OpenCode, Claude Code, Codex, Gemini CLI
- [ ] **Task queue with scheduling** — "run tests at 2am", "retry failed agent 3 times"
- [ ] **Slack/Discord webhooks** — agent finishes → notification in team chat
- [ ] **Multi-user + RBAC** — per-project tokens, read-only access, audit log
- [ ] **Artifact store** — agents produce files, results, logs → central archive
- [ ] **Postgres migration** — SQLite for solo, Postgres for multi-user teams
- [ ] **Prompt template library** — save/share common prompts (review PR, write tests, refactor)

---

## How to use this list

1. **Pick one 🔴 item** — ship it, merge, feel good
2. **Pick one 🟠 item** — repeat
3. After all 🔴+🟠 are done, armada is "release-ready"
4. After all 🟡 are done, armada is "production-grade"
5. 🟢 items expand the audience
6. 🔵 items make it feel polished

**Rule**: Always have exactly ONE item in progress. Finish before starting next.

## 🚀 Cloud / Dedicated Machine (v1.5)

> The current model: armada runs on your laptop. Agents use your laptop's CPU/RAM, die on sleep, and aren't reachable when you close the lid.
> The target: armada runs on a $20/mo cloud VM or a dedicated mini-PC in your closet. Agents run 24/7. You connect from any device.

### Deployment targets

| Option | Cost | Setup | Best for |
|--------|------|-------|----------|
| **Hetzner CX32** (4 vCPU, 8GB) | ~$8/mo | 1h | 3-5 agents, light coding |
| **Hetzner AX42** (8 vCPU, 16GB) | ~$40/mo | 1h | 10+ agents, heavy workflows |
| **Mac Mini M1/M2 on desk** | $500 once | 1h | Always-on, no cloud bill |
| **Raspberry Pi 5 (8GB)** | $80 once | 2h | Light agents, always on, zero cost |
| **Fly.io / Railway** | ~$5-20/mo | 2h | No server management |
| **GitHub Codespaces** | Free tier | 30min | Quick try, not permanent |

### What needs to change

- [ ] **TLS everywhere** — Let's Encrypt auto-renew. No more "token over HTTP." Cloud means public internet.
- [ ] **`armada --share` via tunnel** — `bore`/`ngrok`/`cloudflared` to expose local server without port forwarding. One command.
- [ ] **`armada deploy <target>`** — `armada deploy hetzner` provisions a VM, installs deps, starts daemon. Ansible or cloud-init.
- [ ] **Sandbox per agent** — Docker container per agent node. Prevents `rm -rf /` accidents, contains network access, isolates filesystem. Agents can only touch their project directory.
- [ ] **SSH agent forwarding into sandbox** — agents need git push. Pass SSH key into container safely (not baked into image).
- [ ] **Resource limits per agent** — `--cpus=2 --memory=4g` per Docker sandbox. One runaway agent doesn't OOM the box.
- [ ] **Persistent volume per agent** — `./armada/workspaces/<node>/` mounted into container. Survives container restart.
- [ ] **Watchdog** — agent dead → restart container with same volume. Agent stuck > 30min → kill + alert.
- [ ] **Cloud-init / Terraform** — single `terraform apply` spins up VM, installs armada, starts dashboard, prints QR.
- [ ] **Automated snapshots** — hourly `sqlite3 .backup` to S3/Backblaze. VM dies → restore state in new VM.
- [ ] **Webhook to start agent** — `POST https://armada.example.com/api/trigger/pipeline-X` from GitHub Actions, Slack, cron.
- [ ] **Usage-based cost tracking** — per-agent CPU hours, API tokens spent. Cloud means you pay for compute + LLM APIs.

### Architecture target

```
┌─────────────────────────────────────────────┐
│  Your laptop / phone / tablet                │
│  Browser → https://armada.example.com        │
└──────────────┬──────────────────────────────┘
               │ HTTPS (TLS)
┌──────────────▼──────────────────────────────┐
│  Cloud VM (Hetzner / Fly.io / Mac Mini)      │
│                                              │
│  ┌──────────────────────────────────────┐   │
│  │  Armada Server (FastAPI + SQLite)     │   │
│  │  Caddy/Nginx reverse proxy + TLS     │   │
│  └──────────┬───────────────────────────┘   │
│             │ docker run --rm ...             │
│  ┌──────────▼───────────────────────────┐   │
│  │  Docker Sandboxes (one per agent)     │   │
│  │  ┌──────┐ ┌──────┐ ┌──────┐         │   │
│  │  │Agent │ │Agent │ │Agent │  ...    │   │
│  │  │  1   │ │  2   │ │  3   │         │   │
│  │  │cpus=2│ │cpus=4│ │cpus=1│         │   │
│  │  │mem=4g│ │mem=8g│ │mem=2g│         │   │
│  │  └──────┘ └──────┘ └──────┘         │   │
│  │  Volumes: ./workspaces/<node>/        │   │
│  └─────────────────────────────────────┘   │
│                                              │
│  ┌──────────────────────────────────────┐   │
│  │  Watchdog + snapshots + metrics       │   │
│  └──────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

### The simplest path (do this first)

1. **`armada --share`** — use `cloudflared tunnel` or `bore` to expose localhost:9100 to a public URL with TLS. Zero config on the server side. Works today on your laptop. (~1h)
2. **`Dockerfile`** — already on the platform list. Build + push to ghcr.io. (~1h)
3. **`docker-compose.yml`** — one file: armada server + caddy for TLS. `docker compose up -d` on any VM. (~1h)
4. **Sandbox per agent** — add `container_mode: docker` to node creation. Orchestrator runs `docker run` instead of `tmux new-window`. (~2 days)

After just step 1, you can share your dashboard URL with anyone. After step 4, you can run untrusted agent prompts safely.

| Item | Time | Category |
|------|------|----------|
| Add CSP header | 15min | 🔴 Security |
| Audit innerHTML → textContent | 1h | 🔴 Security |
| Clear env vars before spawn | 1h | 🔴 Security |
| Error page | 1h | 🟠 Reliability |
| `/health` endpoint | 30min | 🟡 Observability |
| SQLite single connection | 2h | 🟠 Reliability |
| Dockerfile | 1h | 🟢 Platform |
| Loading states | 1h | 🔵 UX |
| Empty states | 1h | 🔵 UX |

**If you only have one evening**: pick the 🔴 quick wins (CSP + innerHTML + env vars). That's ~2h and closes the scariest security gaps.
