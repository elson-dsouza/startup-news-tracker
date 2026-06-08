#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../services/dashboard"

if [ ! -d node_modules ]; then
  npm install
fi

npm run dev -- --hostname 0.0.0.0 --port 3000
