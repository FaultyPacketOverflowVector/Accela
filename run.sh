#!/bin/bash
cd "$(dirname "$(realpath "$0")")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

set +eu
# Check if notify-send exists globally
command -v notify-send &> /dev/null
NOTIFY_SEND_AVAILABLE=$?
set -eu

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
    set +eu
    if [ "$NOTIFY_SEND_AVAILABLE" -eq 0 ]; then
        notify-send -t 5000 "INFO" "$1" 2>/dev/null
    fi
    set -eu
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    set +eu
    if [ "$NOTIFY_SEND_AVAILABLE" -eq 0 ]; then
        notify-send -t 5000 -u normal "WARNING" "$1" 2>/dev/null
    fi
    set -eu
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
    set +eu
    if [ "$NOTIFY_SEND_AVAILABLE" -eq 0 ]; then
        notify-send -t 5000 -u critical "ERROR" "$1" 2>/dev/null
    fi
    set -eu
}

# Parse command line arguments
SETUP_VENV=false
PYTHON_ARGS=()

for arg in "$@"; do
    if [ "$arg" = "--venv" ]; then
        SETUP_VENV=true
    else
        PYTHON_ARGS+=("$arg")
    fi
done

setup_venv() {
    # Create virtual environment
    python3 -m venv .venv
    
    # Activate virtual environment
    source .venv/bin/activate
    
    # Install requirements
    if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt
    else
        log_warn "requirements.txt not found, skipping pip install"
    fi	
}

if [ "$SETUP_VENV" = true ]; then
    log_info "Setting up virtual environment and installing dependencies"
    setup_venv
else
    # Check if virtual environment already exists and activate it if it does
    if [ -d ".venv" ] && [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
    else
        log_warn "No virtual environment found, creating"
        setup_venv
    fi
fi

# Run the main script with preserved environment
# This ensures DISPLAY, WAYLAND_DISPLAY, PATH, etc. are preserved
# which is needed for Qt GUI and Wine
# Pass all remaining command-line arguments through to the Python script
exec python src/main.py "${PYTHON_ARGS[@]}"
