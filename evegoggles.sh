#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "Virtualenv not found. Run ./install.sh first."
    exit 1
fi

source "$VENV_DIR/bin/activate"
cd "$SCRIPT_DIR"

# Force X11 backend - Wayland does not support window.move(), opacity or XGrabKey
export QT_QPA_PLATFORM=xcb
export GDK_BACKEND=x11

exec python run.py "$@"
