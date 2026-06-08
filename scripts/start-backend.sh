#!/usr/bin/env bash
set -euo pipefail

docker compose up --build postgres migrate backend-api ingester
