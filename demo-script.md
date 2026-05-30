# Armada Demo Video Script
# Target: 2-3 minutes
# Record: QuickTime or Kap, then narrate and cut

---

## INTRO (15s)
[Show terminal with "armada" ASCII art or just a clean prompt]

"Armada lets you manage multiple AI coding agents as a visual hierarchy.
You can see what each one is doing, spawn children, and kill entire
trees — all from a web dashboard. Let me show you."

---

## STARTUP (15s)
[Type: armada start]

"I run `armada start` to launch the server daemon. It opens the dashboard
automatically."

[Cut to browser, show dashboard at http://127.0.0.1:9100]

"This is the dashboard. Left sidebar shows the node tree. Right panel
shows details for whatever node you select."

---

## PROJECTS (20s)
[Click "Projects" section, click "+ Add"]

"First I register a project. I give it an ID, a name, and a path.
This is where my code lives."

[Fill in: id=shipping-api, name=Shipping API, path=/Users/.../shipping-api]

"Projects show up in the sidebar. I can create nodes that run in
any registered project."

---

## CREATE NODES (40s)
[Click "+ Node" in sidebar header]

"Now I create agents. Give them a name or leave it blank for an
auto-generated one. Pick the project, choose the agent type — Open Code,
Claude Code, or just Bash."

[Create three nodes: Architect, then Code-Reviewer and Test-Writer as children]

"Architect is my root node. Code-Reviewer and Test-Writer are children.
They appear in the tree immediately. Each one gets a unique color."

---

## TREE + STATUS (25s)
[Show the tree with expandable children]

"The dashboard polls every ten seconds. You can see status — active,
idle, error — right in the tree."

[Click Architect, show detail panel]

"Click any node to see its full activity log. This shows every status
report the agent has sent. The latest message tells you what it's doing
right now."

---

## ATTACH TO A NODE (15s)
[Click Architect, then "Attach"]

"Attach opens a terminal tab directly connected to the agent's tmux
window. For Open Code or Claude Code agents, it auto-starts with
armada skills loaded and begins reporting status immediately."

---

## CASCADE KILL (20s)
[Click Architect, then "Kill"]

"Killing a parent node cascades to all its children. One click,
the entire subtree is gone."

[Show tree empty]

"All agent windows are closed, all records are marked dead.
Clean and simple."

---

## CLOSE (15s)
[Show the README or GitHub repo]

"Armada is open source. Install with pip, one command to set up skills,
and you're ready to orchestrate a fleet of AI agents from a single
dashboard."

[Show: armada setup && armada start]

"Link in the description. Thanks for watching."
