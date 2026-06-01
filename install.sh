#!/bin/bash
# Armada — one-command install
# Usage: bash install.sh

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
BIN_DIR="$PROJECT_DIR/bin"

echo ""
echo "⚓ Armada Installer"
echo "═══════════════════"
echo ""

# 1. Check prerequisites
echo "1/4  Checking prerequisites..."

if ! command -v python3 &>/dev/null; then
    echo "  ✗ python3 not found. Install with: brew install python3"
    exit 1
fi

if ! command -v tmux &>/dev/null; then
    echo "  ✗ tmux not found. Install with: brew install tmux"
    exit 1
fi

echo "  ✓ python3 $(python3 --version 2>&1)"
echo "  ✓ tmux $(tmux -V 2>&1)"

# 2. Create virtual environment and install
echo ""
echo "2/4  Installing Python package..."

if [ -d "$VENV_DIR" ] && ! "$VENV_DIR/bin/python3" -c "" 2>/dev/null; then
    echo "  ⚠ Corrupt venv detected, recreating..."
    rm -rf "$VENV_DIR"
fi

if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
"$VENV_DIR/bin/pip" install -e "$PROJECT_DIR" --quiet
echo "  ✓ armada-ai installed"

# 3. Add to PATH
echo ""
echo "3/4  Adding armada to PATH..."

SHELL_RC=""
case "$SHELL" in
    */zsh)   SHELL_RC="$HOME/.zshrc" ;;
    */bash)  SHELL_RC="$HOME/.bashrc" ;;
    *)       SHELL_RC="$HOME/.profile" ;;
esac

PATH_LINE="export PATH=\"$BIN_DIR:\$PATH\""

if grep -qF "$PATH_LINE" "$SHELL_RC" 2>/dev/null; then
    echo "  ✓ Already in $SHELL_RC"
else
    echo "$PATH_LINE" >> "$SHELL_RC"
    echo "  ✓ Added to $SHELL_RC"
fi
export PATH="$BIN_DIR:$PATH"

# 4. Install skills
echo ""
echo "4/4  Installing agent skills..."

armada setup 2>/dev/null || true
echo "  ✓ Skills installed"

# Done
echo ""
echo "═══════════════════"
echo "  Armada installed!"
echo ""
echo "  Start:    armada start"
echo "  Dashboard: http://127.0.0.1:9100"
echo ""
echo "  Open a new terminal or run:"
echo "    source $SHELL_RC"
echo "═══════════════════"
echo ""
