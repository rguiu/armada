# Armada Demo Tape
# Generate with: brew install vhs && vhs demo.tape
#
# VHS generates a clean terminal GIF — no screen recording needed.

Output demo.gif

Set Theme "Catppuccin Mocha"
Set Width 800
Set Height 500
Set FontSize 14
Set Padding 20
Set Framerate 24

# Ensure a clean state
Hide
Type "tmux kill-server 2>/dev/null; rm -rf ~/.armada /tmp/armada-demo; true"
Enter
Sleep 500ms
Show

# Title
Type "# Armada — Agent Orchestration Demo"
Enter
Sleep 1s
Type "# Starting server..."
Enter
Sleep 500ms

Type "armada start"
Sleep 2s
Enter
Sleep 1s

# Register projects
Type "# Register a project"
Enter
Sleep 500ms

Type "curl -s -X POST http://127.0.0.1:9100/api/project-labels -H 'Content-Type: application/json' -d '{\"id\":\"api\",\"name\":\"Shipping API\",\"path\":\"/tmp/armada-demo\"}'"
Enter
Sleep 800ms
Type "echo 'ok'"
Enter
Sleep 500ms

# Create nodes
Type "# Create an orchestrator node"
Enter
Sleep 500ms

Type 'curl -s -X POST http://127.0.0.1:9100/api/nodes -H "Content-Type: application/json" -d '"'"'{"name":"Architect","project_label_id":"api","agent_type":"bash"}'"'"''
Enter
Sleep 800ms
Type "# Architect created (id=1, root node)"
Enter
Sleep 1s

Type "# Spawn worker children"
Enter
Sleep 500ms

Type 'curl -s -X POST http://127.0.0.1:9100/api/nodes -H "Content-Type: application/json" -d '"'"'{"name":"Code-Reviewer","parent_id":1,"project_label_id":"api","agent_type":"bash"}'"'"''
Enter
Sleep 500ms

Type 'curl -s -X POST http://127.0.0.1:9100/api/nodes -H "Content-Type: application/json" -d '"'"'{"name":"Test-Writer","parent_id":1,"project_label_id":"api","agent_type":"bash"}'"'"''
Enter
Sleep 1s

# Show the tree
Type "# View the full hierarchy"
Enter
Sleep 500ms

Type "curl -s http://127.0.0.1:9100/api/tree | python3 -m json.tool"
Enter
Sleep 1500ms

# Simulate agent reports
Type "# Agents report status via curl hooks"
Enter
Sleep 500ms

Type 'curl -s -X POST http://127.0.0.1:9100/api/report -H "Content-Type: application/json" -d '"'"'{"name":"Architect","status":"active","message":"analyzing API structure"}'"'"''
Enter
Sleep 300ms

Type 'curl -s -X POST http://127.0.0.1:9100/api/report -H "Content-Type: application/json" -d '"'"'{"name":"Code-Reviewer","status":"active","message":"reviewing models.py"}'"'"''
Enter
Sleep 300ms

Type 'curl -s -X POST http://127.0.0.1:9100/api/report -H "Content-Type: application/json" -d '"'"'{"name":"Test-Writer","status":"active","message":"writing integration tests"}'"'"''
Enter
Sleep 1s

# Cascade kill
Type "# Cascade kill — parent kills all children"
Enter
Sleep 500ms

Type "curl -s -X DELETE http://127.0.0.1:9100/api/nodes/1"
Enter
Sleep 800ms
Type "# All 3 agents killed"
Enter
Sleep 500ms

Type 'curl -s http://127.0.0.1:9100/api/tree'
Enter
Sleep 500ms
Type "# Tree is empty []"
Enter
Sleep 1s

# Wrap up
Type "# Done. Dashboard at http://127.0.0.1:9100"
Enter
Sleep 1s

Type "armada stop"
Enter
Sleep 500ms
