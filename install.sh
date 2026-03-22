#!/usr/bin/env bash
set -e

VENV_DIR="$(dirname "$0")/.venv"

echo "=== EveGoggles Installer ==="
echo ""

# ── System packages ───────────────────────────────────────────────────────────
echo "[1/3] Installing system packages..."
if command -v dnf &>/dev/null; then
    sudo dnf install -y \
        ImageMagick \
        xdotool \
        wmctrl \
        python3-pip \
        python3-devel \
        gcc \
        libxcb \
        xcb-util-wm \
        2>/dev/null || true
elif command -v apt &>/dev/null; then
    sudo apt update -qq
    sudo apt install -y \
        imagemagick \
        xdotool \
        wmctrl \
        python3-pip \
        python3-venv \
        python3-dev \
        gcc \
        libxcb1 \
        2>/dev/null || true
else
    echo "  Unknown package manager — install manually: ImageMagick, xdotool, wmctrl, python3-devel, gcc"
fi
echo "  System packages done."
echo ""

# ── Python virtualenv ─────────────────────────────────────────────────────────
echo "[2/3] Setting up Python environment in .venv ..."
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"
pip install --upgrade pip --quiet
pip install \
    "PyQt6>=6.4.0" \
    "python-xlib>=0.33" \
    "ewmh>=0.1.6" \
    "Pillow>=10.0.0"
# python-mss optional (no Python 3.14 support yet)
pip install "python-mss" 2>/dev/null \
    && echo "  python-mss installed (fast capture)" \
    || echo "  python-mss not available — ImageMagick fallback active"
echo "  Python packages done."
echo ""

# ── Desktop shortcut ──────────────────────────────────────────────────────────
echo "[3/3] Creating desktop shortcut..."
DESKTOP_FILE="$HOME/.local/share/applications/evegoggles.desktop"
mkdir -p "$HOME/.local/share/applications"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Name=EveGoggles
Comment=EVE Online multi-client window manager
Exec=$(dirname "$0")/evegoggles.sh
Type=Application
Categories=Game;Utility;
StartupNotify=false
EOF
chmod +x "$DESKTOP_FILE"
echo "  Desktop shortcut created: $DESKTOP_FILE"
echo ""

echo "=== Installation complete! ==="
echo "Start EveGoggles met:  ./evegoggles.sh"
