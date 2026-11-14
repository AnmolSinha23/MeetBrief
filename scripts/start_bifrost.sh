#!/usr/bin/env bash
set -e

echo "=============================================="
echo " Starting Bifrost Gateway (http://localhost:8080)"
echo "=============================================="

if ! command -v npx &> /dev/null; then
    echo "ERROR: 'npx' command not found."
    echo "Please install Node.js (v18+) from https://nodejs.org"
    exit 1
fi

echo "Running: npx -y @maximhq/bifrost"
echo "Dashboard will be available at: http://localhost:8080"
echo "Press Ctrl+C to stop."
npx -y @maximhq/bifrost
