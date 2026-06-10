# Armada — Design & UX Ideas

Quick, practical ideas to make the dashboard nicer and more usable. Grouped by effort level.

---

## Quick Wins (< 1 hour each)

### Polish & Micro-interactions

| # | Idea | Why |
|---|---|---|
| 1 | **Smooth expand/collapse** — `max-height` transition on `.children` (300ms ease). Currently it's instant. | Makes the tree feel alive |
| 2 | **Hover tooltips** — Add `title` attributes to status dots ("Active", "Idle", "Pending", "Dead"), cost badges, drag handle | Reduces mystery for new users |
| 3 | **Empty states with personality** — Instead of "No nodes yet", show a small illustration or ASCII art fleet of ships | Makes first-open feel intentional, not broken |
| 4 | **Loading skeleton** — Show 3-4 gray pulsing rows while tree fetches instead of blank sidebar | Prevents "is it loading or broken?" |
| 5 | **Toast with icon** — Add a checkmark/cross prefix to toast messages for instant recognition | Scannable feedback |
| 6 | **Button loading states** — Show spinner on "Create" button while node is being created, disable double-click | Prevents accidental duplicates |
| 7 | **Click feedback on tree nodes** — Subtle background flash (50ms) on click for tactile confirmation | Makes interaction feel responsive |
| 8 | **Favicon** — Add a ship/wave emoji as favicon (even if just an SVG in HTML) | Browser tab recognition |

### Information Clarity

| # | Idea | Why |
|---|---|---|
| 9 | **Status legend** — Tiny row under stats bar showing color meanings: green=active, yellow=pending, gray=idle, red=error | Onboarding for new users |
| 10 | **Relative time everywhere** — Show "Created 2h ago" instead of full ISO timestamp; add "Killed 5m ago" for dead nodes | Scannable at glance |
| 11 | **Truncated messages with expand** — "Spawning 3 workers for the shipping..." + click to see full | Tree stays compact |
| 12 | **Cost warning color** — Cost badge turns amber at $1, red at $5 | Quick cost awareness |
| 13 | **Node count in title** — Dashboard title: "Fleet (4 active, 2 pending)" instead of just "Fleet" | Browser tab glance value |
| 14 | **Terminal tab shows node name** — Instead of "Terminal · node 5", show "Terminal · architect" | Easier to track which terminal you're in |

---

## Medium Effort (1-3 hours each)

### Better Layout

| # | Idea | Why |
|---|---|---|
| 15 | **Resizable sidebar** — Drag handle on sidebar right edge to resize between 200px-450px. Persist to localStorage | Every dashboard needs this |
| 16 | **Collapsible sidebar sections** — "Projects" and "Connect Phone" start collapsed with chevron toggle, remember state | Sidebar stays clean on mobile |
| 17 | **Split view: tree + detail side by side** — On wide screens (>1200px), show tree and detail panel side-by-side like a mail client. Currently you pick a node and lose sight of the tree | Power user dream |
| 18 | **Floating mini-tree** — When detail panel is open on mobile, show a small floating tree button in corner that opens a dropdown | Quick node switching without going back |
| 19 | **Terminal as collapsible bottom drawer** — Instead of replacing detail, terminal slides up from bottom as a resizable drawer (like VS Code terminal) | Keep context while viewing terminal |
| 20 | **Fullscreen terminal mode** — Button to expand terminal to full viewport (like `Cmd+K` in VS Code) | Immersive terminal work |

### Smarter Tree

| # | Idea | Why |
|---|---|---|
| 21 | **Sort options** — Dropdown above tree: "Default", "A-Z", "Status (active first)", "Newest", "Cost (highest)". Persist selection | Finding nodes in a fleet of 20+ |
| 22 | **Group by project** — Toggle to group nodes under project headers in tree ("shipping-api" -> architect, reviewer, tests) | Clearer than mixed flat tree |
| 23 | **Collapse all / Expand all** — Two small buttons above tree, plus "Collapse to depth 1" | Tree management at scale |
| 24 | **Inline rename** — Double-click node name to edit inline (calls PATCH endpoint) | Faster than kill+recreate |
| 25 | **Node context actions on hover** — Show small action icons (terminal, attach, kill) on right side of node row on hover, no right-click needed | Discovery for new users |
| 26 | **Drag preview** — Show a ghost of the dragged node with name label while dragging | Visual clarity during re-parenting |
| 27 | **Multi-select with Shift+Click** — Range select like a file manager (click first, shift+click last) | Batch operations at scale |

### Keyboard Power

| # | Idea | Why |
|---|---|---|
| 28 | **`/` to focus search** — Press `/` anywhere (when not in input) to focus tree search | Vim muscle memory |
| 29 | **`Cmd+K` command palette** — Searchable list: "New node", "Kill all idle", "Show cost report", "Attach to...", "Dark/Light theme", keyboard shortcuts | The one power user feature every app needs |
| 30 | **`?` shows keyboard shortcuts modal** — List all shortcuts in a clean modal | Discovery |
| 31 | **`Space` to toggle checkbox** — Select/deselect nodes quickly with keyboard | Efficient batch ops |
| 32 | **`Ctrl+D` to close terminal** — When terminal is focused | Terminal muscle memory |
| 33 | **`g g` / `G` for first/last node** — Vim-style tree navigation | Power users |

### Detail Panel Enhancement

| # | Idea | Why |
|---|---|---|
| 34 | **Tabbed detail panel** — "Activity Log" / "Terminal" / "Logs" as tabs instead of terminal replacing everything | Clear mental model |
| 35 | **Quick action buttons row** — Pause, Resume, Restart, Clone as icon buttons above node meta | Actions at fingertips |
| 36 | **Cost chart** — Tiny inline sparkline showing cost over the agent's lifetime (last 20 reports as tiny bars) | Visual cost awareness |
| 37 | **"Copy command" on log entries** — Each log entry showing a command gets a copy icon | Reuse prompts |
| 38 | **Collapsible log entries** — Long log messages truncated to 1 line, click to expand | Clean detail panel |
| 39 | **Agent timeline visualization** — Horizontal timeline bar showing status changes over time (green blocks for active, yellow for pending, gray for idle) | See agent's entire session at a glance |
| 40 | **Workspace path display** — Show the project path with a "Open in Finder/Terminal" button | Context for where the agent works |

---

## Higher Effort (1-3 days each)

### Visual Identity & Polish

| # | Idea | Why |
|---|---|---|
| 41 | **Light theme** — Toggleable, auto-detected from OS preference, persists. Light background `#ffffff`, subtle shadows, same color scheme | Half of developers use light themes |
| 42 | **Accent color picker** — Let users pick from 8 accent colors (blue, green, purple, orange, etc.). Persists to localStorage | Personalization = attachment |
| 43 | **Animated tree connections** — Subtle CSS animations when nodes change status (dot pulses briefly, branch line draws in) | Makes status changes visible |
| 44 | **Status transitions with animation** — When a node goes active→pending, the badge smoothly transitions color with a 200ms ease | Polished feel |
| 45 | **Particle/fleet metaphor** — Empty state shows small animated dots representing "ships" (agents) waiting to be launched. Create node = ship launches. Kill = ship docks | Memorable branding |
| 46 | **Sound design** — Different subtle sounds for: node created (positive chirp), node pending (alert ping - already have this), node killed (soft thud), error (buzz) | Multi-sensory feedback |

### Mobile Excellence

| # | Idea | Why |
|---|---|---|
| 47 | **Bottom tab bar** — Mobile layout: bottom tabs for "Tree", "Detail", "Terminal" with icons. Swipe between them | Native app feel |
| 48 | **Pull-to-refresh** — Swipe down on tree to refresh. Visual indicator like iOS/macOS | Mobile muscle memory |
| 49 | **Swipe actions on nodes** — Swipe left → Kill, swipe right → Attach (iOS-style) | Touch-native interactions |
| 50 | **PWA install prompt** — "Add to Home Screen" banner after 2 visits (service worker already exists) | App-store-free distribution |
| 51 | **Mobile-optimized terminal** — Larger touch targets for keys, gesture for scrolling, double-tap to select text | Terminal on phone is currently hard to use |
| 52 | **Haptic feedback** — On mobile, vibrate briefly when node changes to pending (respects silent mode) | Phone in pocket awareness |

### Data & Insights

| # | Idea | Why |
|---|---|---|
| 53 | **Dashboard stats page** — Alternative view: cards showing cost per project, tokens used today, most active agents, average response time | Quick overview for multi-agent sessions |
| 54 | **Cost timeline chart** — Line chart of cumulative cost over time, per project filterable | "Where is my money going?" |
| 55 | **Weekly summary** — "This week: $12.34 spent across 8 agents, 45 tasks completed, 3 permission requests" | Retrospective value |
| 56 | **Export reports** — Button to download all logs as CSV/JSON for a node or project | Share with team, debugging |
| 57 | **Alerts & thresholds** — Set cost cap per project, get toast when approaching limit. "Agent shipping-api-001 has used $5.00 of its $10.00 budget" | Cost control |

### Multi-node Workflows

| # | Idea | Why |
|---|---|---|
| 58 | **Node templates** — "Save as template" from a node's config. Quick-create: "PR Reviewer" template (claude + `/review` prompt + shipping-api project) | Repeatable workflows |
| 59 | **Task queue view** — See pending prompts waiting to be sent to nodes, with reorder and cancel | Orchestrator workflow visibility |
| 60 | **Bulk create** — "Create 3 review agents for project X" with one form | Launch fleets, not boats |
| 61 | **Orchestration recipes** — Pre-built patterns: "PR Review (3 agents)", "Test Suite (2 agents)", "Code Exploration (5 agents)". One-click deploy | New user value proposition |
| 62 | **Node groups** — Tag nodes with custom groups: "Frontend", "Backend", "Urgent". Filter tree by group | Organize large fleets |

### Accessibility & Inclusion

| # | Idea | Why |
|---|---|---|
| 63 | **Screen reader labels** — Add `aria-label` to tree nodes, status badges, action buttons. Role attributes | Blind developers exist |
| 64 | **Focus indicators** — Visible focus ring on all interactive elements (currently some elements lack focus styles) | Keyboard navigation |
| 65 | **Reduced motion mode** — `@media (prefers-reduced-motion)` disables all animations and transitions | Accessibility |
| 66 | **High contrast mode** — Increased contrast toggle that boosts text/background ratios beyond WCAG AA | Visual impairment |
| 67 | **Font size controls** — Small/Medium/Large toggle in settings, persists to localStorage | Aging eyes, high-DPI screens |

---

## Priority: What To Build First

### This week (highest impact/effort ratio)

1. Loading skeleton (#4) — 30 min
2. Toast with icons (#5) — 15 min
3. `?` keyboard shortcuts modal (#30) — 1h
4. `/` to focus search (#28) — 10 min
5. `Cmd+K` command palette (#29) — 2h
6. Sort options in tree (#21) — 1h
7. Smooth expand/collapse (#1) — 15 min
8. Favicon (#8) — 10 min
9. Terminal bottom drawer (#19) — 2h
10. Cost warning colors (#12) — 15 min

### Next week

11. Resizable sidebar (#15) — 1h
12. Tabbed detail panel (#34) — 2h
13. Split view on wide screens (#17) — 3h
14. Light theme (#41) — 2h
15. Empty states with personality (#3) — 1h

### This month

16. Node templates (#58) — 1 day
17. Cost timeline chart (#54) — 1 day
18. Bottom tab bar for mobile (#47) — 1 day
19. Swipe actions on nodes (#49) — 1 day
20. Orchestration recipes (#61) — 2 days

---

*Focus on the "This week" list to get the dashboard from "functional" to "delightful" fast.*
