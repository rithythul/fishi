#!/bin/bash
# Load NVM and use Node 22
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
nvm use 22

# Kill ALL blocking processes more aggressively
echo "Cleaning up old processes..."
pkill -9 -f "python run.py" 2>/dev/null
pkill -9 -f "vite" 2>/dev/null
sleep 2

# Run bun dev
exec bun dev
