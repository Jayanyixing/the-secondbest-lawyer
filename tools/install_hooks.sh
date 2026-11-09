#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

git config core.hooksPath .githooks
chmod +x .githooks/pre-push
echo "已启用 .githooks/pre-push：git push 前自动运行 python3 tools/check_all.py --fast"
