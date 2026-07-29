#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
WEB_DIR="$PROJECT_DIR/web"

if ! curl -sf "${NEO4J_HTTP_URL:-http://localhost:7474}" >/dev/null; then
  echo "Neo4j is not reachable. Start it with:"
  echo "  docker compose up -d"
  exit 1
fi

if [[ ! -d "$WEB_DIR/node_modules" ]]; then
  npm install --prefix "$WEB_DIR"
fi

cd "$WEB_DIR"
exec npm run dev
