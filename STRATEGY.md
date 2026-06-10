# Armada — Strategy & Release Roadmap

**Date:** 2026-06-06
**Sources:** Internal product analysis, sandbox hardening audit, competitive landscape

---

## 1. What Armada Is

A web dashboard that lets you run and monitor multiple AI coding agents (Claude Code, OpenCode) in parallel from any device — phone, tablet, laptop. It wraps agents in persistent tmux sessions so they survive disconnects, and provides real-time status, live terminals, and delegation workflows.

**Core insight:** Running 3-10 AI agents at once is a real daily problem for power users. No existing tool solves this well.

---

## 2. Target Audience — Who Actually Needs This?

| Segment | Need | Willingness |
|---|---|---|
| **AI power users** (freelancers, indie devs) | Run 5+ agents across projects, monitor from phone | High — they already feel the pain daily |
| **Small teams** (2-10 devs sharing an agent fleet) | Visibility into who's running what, shared dashboards | Medium — currently use Slack threads |
| **AI-native startups** (build with Claude/OpenCode) | Orchestrate multi-agent workflows, cost tracking | High — agents are their CI pipeline |
| **Open-source maintainers** | Review PRs with AI agents across repos | Medium — niche but vocal audience |
| **Enterprise** (legal/security constraints) | On-premise fleet management, audit trails, sandboxing | Low — they use Cursor/Bedrock cloud instead |

**Primary target:** AI power users who already use Claude Code or OpenCode daily. ~10K-50K people exist today, growing fast.

---

## 3. Paint Points You Actually Solve

| Pain point | Current state | Armada solution |
|---|---|---|
| Losing track of agent sessions | 8 terminal tabs, scrolling up to find "which one was reviewing auth?" | Dashboard shows all agents with status, message, activity log |
| Missing permission prompts | Agent sits idle waiting for "approve?" while you're in another tab | Pulsing yellow badge in sidebar, browser notification |
| Want to monitor from phone | SSH + tmux attach on a phone keyboard is hell | QR scan → full web terminal, reactive layout |
| Agents crash on laptop sleep | SSH drops, tmux dies without careful setup | Daemonized tmux session survives everything |
| Want to delegate work | Manually copy-paste prompts between terminal windows | Orchestrator spawns workers, sends tasks via API |
| No idea what agents cost | Zero visibility into API spend | Per-node cost tracking (already implemented) |
| Starting agents is tedious | Open new terminal, cd, source venv, run agent, type prompt | One click in dashboard, optional initial prompt |

---

## 4. Competitive Landscape — How You Compare

### Direct (agent fleet managers)

| Tool | Dashboard | Phone | Persistence | Multi-agent | Price |
|---|---|---|---|---|---|
| **Armada** | Web, real-time | QR scan | tmux sessions | Unlimited | Free/OSS |
| Claude Code Workflows | CLI-only | No | In-process | Capped ~16 | Bundled |
| Cursor BG Agents | In-IDE | No | Cloud sessions | Yes | $20/mo |

### Framework-level (not direct competitors)

| Tool | What it does | Gap Armada fills |
|---|---|---|
| CrewAI / AutoGen / LangGraph | Build multi-agent pipelines programmatically | Armada doesn't replace these — it monitors and controls agents built with any tool |
| Aider / OpenCode | Single-agent CLI tools | Armada wraps N instances of these and gives you a dashboard |

### Key insight
**Claude Code and Cursor are eating this space from both ends.** Claude Code adds built-in subagents. Cursor adds cloud background agents. Armada's defensible niche is: *managing existing CLI agents across multiple projects, with phone access.* Neither first-party tool does that.

---

## 5. Distribution Strategy — Web vs Desktop vs Phone

### Recommendation: Web-first, with optional wrappers

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **Web dashboard** (current) | Works on everything. Zero install for viewers. QR code = instant access. Easy to iterate | Requires server running. No native OS integration (notifications, tray icon) | **Keep as primary.** It's already good |
| **Electron / Tauri desktop app** | Native notifications, tray icon, auto-start, offline mode, install experience | Heavy bundle (Electron ~150MB). Double maintenance (web + desktop). Slower to ship | **Not worth it yet.** Web + PWA covers 90% of desktop use |
| **Phone app (React Native / Swift)** | Native gestures, push notifications, camera for QR scan, background monitoring | Full separate codebase. App Store review. Users don't want another app | **No.** Web is already mobile-optimized. Add PWA manifest instead |
| **PWA (Progressive Web App)** | Install to home screen, push notifications, offline cache, no app store | Limited OS integration (no tray icon, no background service) | **Yes — low effort, high impact.** Already have the web app. Just add manifest + service worker |
| **CLI** (current) | Power users love it. No browser needed. Pipes into other tools | Less discoverable. Hard to show off | **Keep and improve.** Add TUI mode (textual/blessed) |
| **Raycast / Alfred extension** | Fits power-user workflow. Natural integration | Niche audience | **Nice to have later** |

### The PWA Sweet Spot

Add a `manifest.json` and a service worker (1 day of work). Users can then:
- "Install" Armada to their phone home screen (no app store)
- Get push notifications when agents need attention
- Open offline-cached dashboard instantly

This is how tools like Home Assistant, Pi-hole, and Jellyfin handle this — web dashboards that feel native.

---

## 6. Features That Make It "Release-Ready"

### v1.0 blockers (must have before calling it 1.0)

| # | Feature | Why it matters |
|---|---|---|
| 1 | **Linux support** | Currently macOS-only. Half the AI dev audience is on Linux. Fix `lsof`, iTerm AppleScript, `fuser` calls |
| 2 | **Server restart recovery** | If the server crashes, agents keep running in tmux but server can't reconnect. Auto-reconnect on restart |
| 3 | **SQLite concurrency fix** | "Database is locked" errors with 8+ nodes. Single connection + serialized access |
| 4 | **Structured agent logs** | Right now you only see the terminal. Need searchable JSONL logs per agent |
| 5 | **PWA manifest** | Install to phone home screen. Push notifications. This is the single highest-impact 1-day task |
| 6 | **Basic error page** | When server restarts, show a "reconnecting..." page instead of blank white |

### v1.1 stretch (post-launch momentum)

| # | Feature | Impact |
|---|---|---|
| 7 | **WebSocket push for tree** | Replace 10s polling with real-time updates. Feels 10x more responsive |
| 8 | **Prompt template library** | Save common prompts. "Review this PR", "Write tests for X", "Refactor Y to use Z pattern" |
| 9 | **Cost guardrails** | Max $/session, auto-kill after N tokens. Running 10 agents gets expensive fast |
| 10 | **Dark/light theme** | Already dark. Light mode for daytime coding |
| 11 | **Task queue** | Schedule prompts. "Run tests at 2am". "Retry failed agent 3 times" |
| 12 | **Slack/Discord webhooks** | Agent finishes → notification in your team's Slack |

### v2.0 vision

| # | Feature |
|---|---|
| 13 | **Multi-server federation** — one dashboard controlling agents across multiple machines |
| 14 | **Agent marketplace** — pre-built orchestrator patterns (PR reviewer, test generator, codebase explorer) |
| 15 | **Replay/timeline** — scrub through agent history like a video, see every decision it made |
| 16 | **Plugin system** — community extensions for different agent types, status extractors |

---

## 7. The "Show It To People" Checklist

What needs to work before you demo this to someone:

| Must work | Current state |
|---|---|
| Install in < 2 minutes | Already — `bash install.sh` |
| Create first agent in 30 seconds | Already — one button click |
| See agent actually doing something | Already — web terminal renders in real time |
| Works on phone | Already — QR scan, responsive layout |
| Doesn't crash/break visibly | **Needs work** — error pages, recovery, Linux support |
| Looks polished | **80% there** — dark theme is clean, sidebar tree is good. Need loading states, empty states, better spacing |
| Security doesn't scare people | **Needs work** — token in URL, no CSP, shared tmux session |

### The Demo Flow

```
1. "Watch this" → armada start → browser opens
2. "Let me add a project" → click + Add → type "my-backend"
3. "Now let's add an agent" → click + Node → "code-reviewer"
4. "Here's it reviewing my PR" → attach → agent starts working
5. "Now from my phone" → show QR → scan → same dashboard, can kill/restart
6. "Let me add two more agents" → architect + test-writer → tree shows 3 agents running
7. "They finish, results are visible" → activity log in detail panel
```

---

## 8. What Other People Do — Patterns Worth Stealing

| Tool | Pattern | Worth stealing? |
|---|---|---|
| **Cursor** | "Rules for AI" — project-specific instructions that auto-inject into agent context | Yes — Armada already has projects, add project-level system prompts |
| **Claude Code** | `/compact` command — summarize and free context | Yes — add a "compact context" button per agent |
| **Windsurf / Cascade** | Agent "memories" — persistent context across sessions | Maybe — Armada agents are stateless by design, but project-level memory could help |
| **OpenInterpreter** | OSS with strong community, runs locally | Already similar audience. Armada could integrate as a backend |
| **Home Assistant** | PWA + companion app, massive plugin ecosystem, local-first | Their distribution model is the template to follow |
| **Jupyter** | Kernel-based, cell-by-cell execution, rich output | Could Armada do cell-by-cell agent execution? Interesting but different |
| **Linear** | Command bar (Cmd+K), keyboard-first UX | Yes — power users use keyboards. Already have some shortcuts |
| **ngrok** | Expose local server to internet with one command | Could Armada offer a `--share` flag that tunnels to a public URL? |

---

## 9. Tech Bets — What To Bet On vs Avoid

| Bet | Rationale |
|---|---|
| **Web as primary UI** | Correct call. Don't build native apps. PWA covers it |
| **Python + FastAPI** | Good. Simple, fast to develop, huge ecosystem. Eventually you'll want Go/Rust for the server but not yet |
| **tmux as backend** | Right for v1, wrong for v2. Combined tmux session is a security and isolation problem. Abstract behind a backend interface now |
| **SQLite** | Right for single-user, wrong for multi-user. Works for v1. Plan migration to Postgres for v2 (multi-tenant) |
| **xterm.js** | Good for terminal rendering. Polling is the bottleneck — fix with WebSocket push |
| **No framework frontend** | 1,100-line single HTML file is unsustainable. At some point you'll need React/Svelte or at minimum split into modules |

---

## 10. Security — What Actually Matters For v1

From the sandbox hardening audit, here's what's *actually scary* and what's fine:

### Fix before showing people

| # | Issue | Why | Effort |
|---|---|---|---|
| 1 | Token in URL → leaks in browser history, screenshots, QR codes | Anyone with the QR photo can access your agents | **1h** — move token to `Authorization` header + short-lived QR tokens |
| 2 | No CSP header | XSS via agent output could exfiltrate token | **15min** — add CSP header |
| 3 | CDN supply chain | xterm.js loaded from jsdelivr/esm.sh. Compromised CDN = compromised dashboard | **1 day** — vendor xterm.js |
| 4 | Tmux session sharing | Agent in one window can access all other windows | **1 day** — separate tmux session per agent |
| 5 | Env var inheritance | Agents see `~/.ssh`, `~/.aws`, all shell env vars | **1h** — clear sensitive vars before spawning |
| 6 | xterm.js `innerHTML` use | Agent output could inject HTML/JS | **1h** — audit `esc()` function, use `textContent` |

### Not urgent for v1

- Rate limiting (useful when you have users, not for solo use)
- AWS Cognito / SSO (only when multi-user)
- Sandbox containers (solo users don't need VM isolation)
- Bedrock integration (until AWS deployment)

---

## 11. Growth Hooks — How To Get First 100 Users

| Tactic | Effort | Expected reach |
|---|---|---|
| **Hacker News "Show HN"** | 2h writing post | 5K-20K views, ~100-500 stars if it resonates |
| **r/ClaudeCode, r/ChatGPTCoding** | 30min cross-post | 200-1K views, niche audience exactly right |
| **YouTube demo** | 2h record + edit | 500-5K views, long tail |
| **Tweet thread** | 1h craft thread | Depends on your following. Tag @Anthropic, @cursor_ai, etc. |
| **OpenCode integration** | Already have skills for OpenCode. Make it a recommended companion tool | Cross-promotion |
| **"Made with Armada" badge** | Add to README of any project where you used agents | Slow growth, social proof |

### The HN Post That Would Work

> **Show HN: Armada — a fleet manager for AI coding agents (web dashboard + phone)**

> I got tired of managing 8 Claude Code sessions across 4 projects. So I built a dashboard that wraps them in tmux and lets me monitor everything from my phone.

> - QR code → scan with phone → live terminal + controls
> - Tree view of all agents with status (active/idle/pending)
> - Delegation: orchestrator spawns workers, collects results
> - Zero config: `armada` → browser opens

> 3K lines of Python. MIT license. Looking for feedback!

---

## 12. Immediate Next Actions (Ordered)

| Priority | Task | Effort | Why first |
|---|---|---|---|
| 1 | **Move token out of URL** — `Authorization: Bearer` header + cookie | 1 hour | Prevents token leakage before you share QR codes |
| 2 | **Add CSP header** | 15 minutes | Defense in depth |
| 3 | **Add error page** — show "server restarting..." instead of blank white | 1 hour | Prevents "it's broken" first impression |
| 4 | **Fix SQLite concurrency** — single connection, serialized access | 2 hours | Fixes "database locked" errors |
| 5 | **Separate tmux sessions per agent** | 1 day | Prevents agent cross-contamination |
| 6 | **PWA manifest + service worker** | 1 day | Install to phone home screen, push notifications |
| 7 | **Linux support** — fix platform-specific code | 1-2 days | Doubles potential audience |
| 8 | **Server restart recovery** — reconnect to running agents | 2 days | Prevents data loss on crash |
| 9 | **Vendor xterm.js** — bundle locally | 1 day | Remove CDN dependency |
| 10 | **Structured agent logs** — JSONL + search API | 1 day | Searchable history, debugging |

---

## 13. The Product DNA — What Armada Should Be

| Is | Is not |
|---|---|
| Monitoring + control plane for agents | A framework for building agents |
| Local-first, zero-config | Cloud-first, sign-up required |
| Works with any agent | Locked to one agent type |
| Power user tool | Beginner-friendly AI wrapper |
| Web dashboard (desktop + phone) | Native app |
| Thin layer over tmux | A replacement for tmux |
| Free / OSS | SaaS with subscriptions |
| "htop for AI agents" | "WordPress for AI apps" |

---

## 14. Why This Project Could Actually Work

1. **Real pain point, daily.** The moment someone runs 3+ agents, they feel it. The problem is growing, not shrinking.

2. **No good solution exists.** Claude Code Workflows is in early beta. Cursor BG agents are IDE-locked. No one has built the "fleet manager" layer.

3. **Defensible niche.** Managing *existing* agents across *multiple* projects from *any device* — no first-party tool targets this. Claude and Cursor build agents, they don't manage external ones.

4. **Low competition cost.** The whole thing is 3K lines of Python. Even if Claude Code adds a dashboard, you invested weeks, not years.

5. **Right timing.** AI coding agents just hit mainstream (mid-2025). Power users are emerging now. The market is fresh and undominated.

6. **Distribution is free.** OSS + HN + Reddit + Twitter. No marketing budget needed if the tool is genuinely good.

---

## 15. Decisions You Need To Make

| Question | Recommendation |
|---|---|
| Web or native app? | **Web + PWA.** Native adds maintenance, doesn't add value yet |
| Phone app? | **No.** Web is mobile-optimized. PWA covers the rest |
| Electron? | **No.** Same as above. Wait until you need tray icon / OS integration |
| Multi-user now or later? | **Later.** Solo/tested with 1-2 co-workers. Multi-user requires auth overhaul |
| Cloud or local-only? | **Local-first for now.** Add `armada --share` (ngrok-style tunnel) before full cloud deployment |
| Monetize now? | **No.** Build usage first. Monetize later with team features (SSO, audit, RBAC) |
| Open-source license? | MIT already. Good. Keep it. |

---

*Generated from analysis of `project-report` and `feat/sandbox-hardening` branches + current codebase audit.*
