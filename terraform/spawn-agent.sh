#!/usr/bin/env bash
# spawn-agent.sh — Spawn or destroy a Flashpoint LXC agent via Terraform.
# Usage:
#   spawn-agent.sh spawn  <vmid> <ip> <tier> "<mission>"
#   spawn-agent.sh destroy <vmid>
#
# All secrets are read from the environment — never hardcode them here.
# Required env (see terraform/README): PVE_USER, PVE_TOKEN_NAME, PVE_TOKEN_VALUE,
# PVE_HOST, PVE_NODE, AS_TEMPLATE_VMID, AS_PGVECTOR_WRITER_PASS,
# AS_GITLAB_URL, AS_GITLAB_PROJECT_ID, AS_GITLAB_TOKEN.

set -euo pipefail

ACTION="${1:-}"
VMID="${2:-}"
PROXMOX_TOKEN="PVEAPIToken=${PVE_USER}!${PVE_TOKEN_NAME}=${PVE_TOKEN_VALUE}"
PROXMOX_API="https://${PVE_HOST}:8006/api2/json"
TF_BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export TF_VAR_proxmox_api_token="${PVE_USER}!${PVE_TOKEN_NAME}=${PVE_TOKEN_VALUE}"
export TF_VAR_decisions_db_pass="${AS_PGVECTOR_WRITER_PASS}"

if [[ -z "$ACTION" || -z "$VMID" ]]; then
  echo "Usage: $0 <spawn|destroy> <vmid> [ip] [tier] [mission]"
  exit 1
fi

pve_api() {
  curl -sk -H "Authorization: $PROXMOX_TOKEN" "$@"
}

if [[ "$ACTION" == "spawn" ]]; then
  IP="${3:?IP required for spawn}"
  TIER="${4:-ephemeral}"
  MISSION="${5:-agent mission}"
  AGENT_NAME="agent-$VMID"
  WORKSPACE="$TF_BASE/agents/$VMID"

  echo "=== Spawning CT $VMID (as-$VMID, $IP, $TIER) ==="
  echo "    Mission: $MISSION"

  echo "--- Stopping agent template (CT ${AS_TEMPLATE_VMID})..."
  pve_api -X POST "$PROXMOX_API/nodes/${PVE_NODE}/lxc/${AS_TEMPLATE_VMID}/status/stop" > /dev/null
  sleep 8

  mkdir -p "$WORKSPACE"
  cp "$TF_BASE/provider.tf" "$WORKSPACE/"

  cat > "$WORKSPACE/backend.tf" << BACKEND
terraform {
  backend "http" {
    address        = "${AS_GITLAB_URL}/api/v4/projects/${AS_GITLAB_PROJECT_ID}/terraform/state/${AGENT_NAME}"
    lock_address   = "${AS_GITLAB_URL}/api/v4/projects/${AS_GITLAB_PROJECT_ID}/terraform/state/${AGENT_NAME}/lock"
    unlock_address = "${AS_GITLAB_URL}/api/v4/projects/${AS_GITLAB_PROJECT_ID}/terraform/state/${AGENT_NAME}/lock"
    username       = "${AS_GITLAB_USER:-root}"
    password       = "${AS_GITLAB_TOKEN}"
    lock_method    = "POST"
    unlock_method  = "DELETE"
    retry_wait_min = 5
  }
}
BACKEND

  cat > "$WORKSPACE/main.tf" << 'MAIN'
module "agent" {
  source     = "../../modules/agent"
  vmid       = var.vmid
  hostname   = var.hostname
  ip_address = var.ip_address
  tier       = var.tier
  mission    = var.mission
}

variable "vmid"       { type = number }
variable "hostname"   { type = string }
variable "ip_address" { type = string }
variable "tier"       { type = string  default = "ephemeral" }
variable "mission"    { type = string  default = "" }

output "agent" {
  value     = module.agent
  sensitive = true
}
MAIN

  cat > "$WORKSPACE/terraform.tfvars" << TFVARS
vmid       = $VMID
hostname   = "as-$VMID"
ip_address = "$IP"
tier       = "$TIER"
mission    = "$MISSION"
TFVARS

  cd "$WORKSPACE"
  terraform init -backend=true -reconfigure > /dev/null 2>&1
  terraform apply -auto-approve

  echo "--- Restarting agent template (CT ${AS_TEMPLATE_VMID})..."
  pve_api -X POST "$PROXMOX_API/nodes/${PVE_NODE}/lxc/${AS_TEMPLATE_VMID}/status/start" > /dev/null

  echo ""
  echo "=== Agent CT $VMID is live ==="
  echo "    Gateway:   http://$IP:18789"
  echo "    SSH:       ssh -J root@${PVE_HOST} root@$IP"
  echo "    State:     ${AS_GITLAB_URL}/api/v4/projects/${AS_GITLAB_PROJECT_ID}/terraform/state/${AGENT_NAME}"

elif [[ "$ACTION" == "destroy" ]]; then
  WORKSPACE="$TF_BASE/agents/$VMID"
  if [[ ! -d "$WORKSPACE" ]]; then
    echo "Error: workspace $WORKSPACE not found"
    exit 1
  fi
  echo "=== Destroying CT $VMID ==="
  cd "$WORKSPACE"
  terraform destroy -auto-approve
  cd - > /dev/null
  rm -rf "$WORKSPACE"
  echo "=== CT $VMID destroyed. Decisions persist in the decisions DB. ==="
else
  echo "Unknown action: $ACTION (use spawn or destroy)"
  exit 1
fi
