#!/usr/bin/env bash
# One-step local dev launcher for Linux / macOS
# Usage: ./dev.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Prerequisites check ────────────────────────────────────────────────────────
for cmd in python3 func azurite; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "ERROR: '$cmd' is not installed or not on PATH."
        echo "See docs/local-development.md for install instructions."
        exit 1
    fi
done

# ── Ensure .venv exists ────────────────────────────────────────────────────────
if [[ ! -d ".venv" ]]; then
    echo "[setup] Creating Python virtual environment..."
    python3 -m venv .venv
    source .venv/bin/activate
    echo "[setup] Installing dependencies..."
    pip install -r requirements.txt --quiet
else
    source .venv/bin/activate
fi

# ── Ensure local.settings.json exists ─────────────────────────────────────────
if [[ ! -f "local.settings.json" ]]; then
    echo "[setup] local.settings.json not found — copying from example..."
    cp local.settings.example local.settings.json
    echo "        Fill in your credentials in local.settings.json, then re-run."
    exit 0
fi

# ── Start Azurite (background) ─────────────────────────────────────────────────
AZURITE_DIR="${TMPDIR:-/tmp}/azurite"
mkdir -p "$AZURITE_DIR"

if pgrep -x azurite &>/dev/null; then
    echo "[azurite] Already running — skipping."
else
    echo "[azurite] Starting in background (logs: $AZURITE_DIR/debug.log)..."
    azurite --location "$AZURITE_DIR" --debug "$AZURITE_DIR/debug.log" &
    AZURITE_PID=$!
    sleep 1
    echo "[azurite] Started (PID $AZURITE_PID)"
fi

# ── Start Azure Function ───────────────────────────────────────────────────────
echo ""
echo "Starting Azure Function host..."
echo "Press Ctrl+C to stop."
echo ""
func start
