#!/bin/bash
# publish.sh — Commit and push write-up posts
# Usage: publish.sh "commit message"
set -euo pipefail

REPO="$HOME/Desktop/joaobonin.com"
MSG="${1:-auto-commit}"

# Remove stale git lock if a previous process crashed
rm -f "$REPO/.git/index.lock"

cd "$REPO"

# Stage all post content, images, and scripts
/usr/bin/git add content/posts/ static/images/ scripts/

# Commit (will fail cleanly if nothing staged)
/usr/bin/git commit -m "$MSG"

# Push
/usr/bin/git push origin main

echo "Done: $MSG"
