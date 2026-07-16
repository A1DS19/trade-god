#!/usr/bin/env bash
#
# Export the swing agent's container logs from the Lightsail host to a local file.
#
# Usage:
#   ./scripts/export_swing_logs.sh [output_file]
#
# Overridable via environment:
#   SSH_KEY    path to the Lightsail private key   (default: ./LightsailDefaultKey-ap-southeast-1.pem)
#   SSH_HOST   user@ip of the Lightsail instance   (default: ubuntu@54.169.100.56)
#   REMOTE_DIR project dir on the host             (default: ~/trade-god)
#
set -euo pipefail

# Resolve repo root so the script works from any working directory.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

SSH_KEY="${SSH_KEY:-$REPO_ROOT/LightsailDefaultKey-ap-southeast-1.pem}"
SSH_HOST="${SSH_HOST:-ubuntu@54.169.100.56}"
REMOTE_DIR="${REMOTE_DIR:-~/trade-god}"
OUTPUT="${1:-$REPO_ROOT/swing-logs.txt}"

if [[ ! -f "$SSH_KEY" ]]; then
  echo "error: SSH key not found at $SSH_KEY" >&2
  exit 1
fi

echo "Exporting swing logs from $SSH_HOST -> $OUTPUT"
ssh -i "$SSH_KEY" "$SSH_HOST" \
  "cd $REMOTE_DIR && docker compose logs --no-color --timestamps swing" \
  > "$OUTPUT" 2>&1

echo "Done — $(wc -l < "$OUTPUT") lines written to $OUTPUT"
