# Armada Demo — VHS tape
# Usage: brew install vhs && vhs demo.tape
# Output: demo.gif (terminal recording, ~3s)

Output demo.gif

Set Theme "Catppuccin Mocha"
Set Width 800
Set Height 500
Set FontSize 14
Set Padding 20
Set Framerate 24
Set PlaybackSpeed 0.8

# Clean slate
Hide
Type "tmux kill-server 2>/dev/null; rm -rf ~/.armada /tmp/armada-demo; mkdir -p /tmp/armada-demo; true"
Enter
Sleep 1s
Show

# Run the demo script (types nothing — runs the full flow)
Type "bash demo.sh"
Enter
Sleep 25s

# Done
Sleep 1s
Type "# Dashboard at http://127.0.0.1:9100"
Enter
Sleep 1s
