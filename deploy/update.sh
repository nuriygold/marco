#!/usr/bin/env bash
# Marco — idempotent droplet update script.
#
# Pull the latest code, refresh Python deps if the lockfile changed, and
# restart the systemd unit only if something actually updated. Safe to run on
# a cron or by hand.
#
# Usage:
#   ./deploy/update.sh              # pull the current branch
#   ./deploy/update.sh main         # check out + pull main before updating
#   ./deploy/update.sh <branch>     # preview any branch on this droplet
#
# Expects the layout described in deploy/README.md:
#   /home/marco/marco/         — git checkout
#   /home/marco/marco/.venv/   — Python virtualenv
#   marco.service              — systemd unit name

set -euo pipefail

REPO_DIR="${MARCO_REPO_DIR:-/home/marco/marco}"
VENV_DIR="${MARCO_VENV_DIR:-$REPO_DIR/.venv}"
SERVICE="${MARCO_SERVICE:-marco}"
BRANCH="${1:-}"

if [[ ! -d "$REPO_DIR/.git" ]]; then
  echo "error: $REPO_DIR is not a git checkout" >&2
  exit 1
fi

cd "$REPO_DIR"

# Optional: switch branches before pulling. Useful for previewing a feature
# branch on the droplet without spinning up a second machine.
if [[ -n "$BRANCH" ]]; then
  echo "▸ switching to branch: $BRANCH"
  git fetch origin "$BRANCH"
  git checkout "$BRANCH"
fi

CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
PREV_SHA=$(git rev-parse HEAD)
PREV_REQ_HASH=$(sha256sum deploy/requirements.txt 2>/dev/null | awk '{print $1}' || echo "none")

echo "▸ pulling origin/$CURRENT_BRANCH"
git pull --ff-only origin "$CURRENT_BRANCH"

NEW_SHA=$(git rev-parse HEAD)
NEW_REQ_HASH=$(sha256sum deploy/requirements.txt 2>/dev/null | awk '{print $1}' || echo "none")

if [[ "$PREV_SHA" == "$NEW_SHA" && -z "$BRANCH" ]]; then
  echo "▸ already up to date ($NEW_SHA) — nothing to do"
  exit 0
fi

# Refresh Python deps only if requirements.txt changed.
if [[ "$PREV_REQ_HASH" != "$NEW_REQ_HASH" ]]; then
  echo "▸ requirements.txt changed — reinstalling"
  "$VENV_DIR/bin/pip" install -q -r deploy/requirements.txt
else
  echo "▸ requirements unchanged — skipping pip install"
fi

echo "▸ restarting $SERVICE"
sudo systemctl restart "$SERVICE"

# Wait briefly and confirm the unit came back up.
sleep 2
if systemctl is-active --quiet "$SERVICE"; then
  echo "✓ $SERVICE is active at $NEW_SHA"
else
  echo "✗ $SERVICE failed to start — check 'journalctl -u $SERVICE -n 50'" >&2
  exit 1
fi
