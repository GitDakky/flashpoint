#!/usr/bin/env bash
# Flashpoint runner deploy — one command to build the agent image, configure and
# start the spawner on a fresh Docker host.
#
# Usage (as root on the runner):
#   ./deploy/runner.sh [--port 2880] [--gateway-host <ip>] [--image flashpoint/agent:latest]
#
# It will:
#   1. check/install Docker (best-effort, Debian/Ubuntu)
#   2. build the agent image from agent/
#   3. write /opt/flashpoint/.env from your answers (or env vars)
#   4. install + start the as-spawner systemd unit
#   5. health-check the API
#
# Secrets come from flags/env, never written into the repo.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR="/opt/flashpoint"
SERVICE="as-spawner"
PORT="${FP_SPAWNER_PORT:-2880}"
IMAGE="${FP_AGENT_IMAGE:-flashpoint/agent:latest}"
GATEWAY_HOST="${FP_GATEWAY_HOST:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port) PORT="$2"; shift 2;;
    --gateway-host) GATEWAY_HOST="$2"; shift 2;;
    --image) IMAGE="$2"; shift 2;;
    *) echo "unknown flag: $1"; exit 1;;
  esac
done

echo "==> Flashpoint runner deploy (repo: $REPO_DIR)"

# 1. Docker
if ! command -v docker >/dev/null 2>&1; then
  echo "==> installing Docker"
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -qq
    apt-get install -y -qq docker.io >/dev/null
    systemctl enable --now docker
  else
    echo "ERROR: no apt-get; install Docker manually and re-run." >&2
    exit 1
  fi
fi
systemctl enable --now docker 2>/dev/null || true

# 2. Build image
echo "==> building agent image: $IMAGE"
docker build -t "$IMAGE" "$REPO_DIR/agent"

# 3. Config
mkdir -p "$INSTALL_DIR"
mkdir -p /var/lib/flashpoint
cp "$REPO_DIR/spawner/spawner.py" "$INSTALL_DIR/spawner.py"

if [[ ! -f "$INSTALL_DIR/.env" ]]; then
  echo "==> writing $INSTALL_DIR/.env (edit later to change)"
  # Default gateway host to this host's primary IP if not supplied
  if [[ -z "$GATEWAY_HOST" ]]; then
    GATEWAY_HOST="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}' | head -1)"
  fi
  cat > "$INSTALL_DIR/.env" <<EOF
FP_SPAWNER_PORT=$PORT
FP_AGENT_IMAGE=$IMAGE
FP_GATEWAY_HOST=$GATEWAY_HOST
FP_DECISIONS_HOST=${FP_DECISIONS_HOST:-}
FP_DECISIONS_PASS=${FP_DECISIONS_PASS:-}
FP_ORCHESTRATOR=${FP_ORCHESTRATOR:-}
FP_REGISTRY_PATH=${FP_REGISTRY_PATH:-/var/lib/flashpoint/registry.jsonl}
FP_REGISTRY_DSN=${FP_REGISTRY_DSN:-}
FP_DEFAULT_MODEL=${FP_DEFAULT_MODEL:-openrouter/anthropic/claude-opus-4-8}
EOF
  chmod 600 "$INSTALL_DIR/.env"
else
  echo "==> keeping existing $INSTALL_DIR/.env"
fi

# 4. systemd unit
cp "$REPO_DIR/spawner/as-spawner.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now "$SERVICE"
systemctl restart "$SERVICE"

# 5. Health check
sleep 2
if curl -fsS -m5 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
  echo "==> spawner healthy on :$PORT"
  curl -fsS -m5 "http://127.0.0.1:$PORT/health"
  echo ""
else
  echo "WARNING: spawner did not answer on :$PORT yet; check 'systemctl status $SERVICE'"
fi

echo "==> done. Spawn an agent:"
echo "    curl -X POST http://$GATEWAY_HOST:$PORT/spawn -H 'Content-Type: application/json' \\"
echo "      -d '{\"mission\":\"test\",\"tier\":\"ephemeral\"}'"
