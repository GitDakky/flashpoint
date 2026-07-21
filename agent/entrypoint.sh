#!/bin/bash
set -e

echo "=== Flashpoint Agent Bootstrap ==="
echo "Agent ID:   ${AS_AGENT_ID:-unset}"
echo "Tier:       ${AS_AGENT_TIER:-ephemeral}"
echo "Mission:    ${AS_MISSION:-none}"
echo "Model:      ${AS_MODEL:-unset}"

if [ -n "$SOUL_CONTENT" ]; then
    echo "$SOUL_CONTENT" | base64 -d > /root/clawd/SOUL.md
fi

if [ -n "$USER_CONTENT" ]; then
    echo "$USER_CONTENT" | base64 -d > /root/clawd/USER.md
fi

cat > /root/clawd/.env << EOF
AS_AGENT_ID=${AS_AGENT_ID:-docker-agent-$$}
AS_AGENT_TIER=${AS_AGENT_TIER:-ephemeral}
AS_MISSION=${AS_MISSION}
AS_ORCHESTRATOR=${AS_ORCHESTRATOR:-}
AS_DECISIONS_HOST=${AS_DECISIONS_HOST:-}
AS_DECISIONS_PASS=${AS_DECISIONS_PASS:-}
EOF

TOKEN="${OPENCLAW_TOKEN:-$(node -e 'console.log(require("crypto").randomBytes(32).toString("hex"))')}"

MODEL="${AS_MODEL:-openrouter/anthropic/claude-opus-4-8}"

openclaw config set gateway.mode local          2>/dev/null || true
openclaw config set gateway.bind lan            2>/dev/null || true
openclaw config set gateway.controlUi.dangerouslyAllowHostHeaderOriginFallback true 2>/dev/null || true
openclaw config set gateway.auth.mode token     2>/dev/null || true
openclaw config set gateway.auth.token "$TOKEN" 2>/dev/null || true
openclaw config set agents.defaults.model "$MODEL" 2>/dev/null || true
openclaw config set agents.defaults.workspace /root/clawd 2>/dev/null || true

# PTC: enable tool orchestration — agents call tools programmatically rather
# than one-at-a-time, keeping intermediate results out of context.
openclaw config set agents.defaults.tools.exec.enabled true 2>/dev/null || true

cat > /root/clawd/MEMORY.md << EOF
# MEMORY.md — ${AS_AGENT_ID:-agent}
Spawned: $(date -u +%Y-%m-%dT%H:%M:%SZ)
Tier: ${AS_AGENT_TIER:-ephemeral}
Mission: ${AS_MISSION:-none}
Model: ${MODEL}
PTC: enabled (Programmatic Tool Calling — orchestrate tools via code, not sequential calls)
EOF

echo "=== Starting OpenClaw gateway (model: $MODEL) ==="
export NODE_OPTIONS="--max-old-space-size=1536"
exec openclaw gateway run \
    --bind lan \
    --port 18789 \
    --allow-unconfigured \
    --token "$TOKEN"
