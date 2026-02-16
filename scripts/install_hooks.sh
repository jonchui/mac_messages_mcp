#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
tracked_hooks="$repo_root/.githooks"
git_hooks="$repo_root/.git/hooks"

if [ ! -d "$git_hooks" ]; then
  echo "❌ .git/hooks not found. Run from a git checkout."
  exit 1
fi

for hook in pre-commit post-commit; do
  src="$tracked_hooks/$hook"
  dst="$git_hooks/$hook"
  if [ ! -f "$src" ]; then
    echo "❌ Missing tracked hook: $src"
    exit 1
  fi
  cp "$src" "$dst"
  chmod +x "$dst"
  echo "✅ Installed $hook"
done

echo
echo "Hooks synced from .githooks -> .git/hooks"
