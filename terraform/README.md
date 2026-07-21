# Flashpoint Terraform — LXC agent path

This directory provisions agents as full LXC containers (each with its own OS,
IP and SSH) cloned from an LXC agent template. Use this when you need per-agent
OS isolation. For raw spawn speed at scale, prefer the Docker spawner in
`../spawner`.

## Layout

| Path | Purpose |
|---|---|
| `modules/agent/` | Reusable `proxmox_virtual_environment_container` module |
| `agents/example/` | Example root module that calls `modules/agent` |
| `spawn-agent.sh` | CLI wrapper: `spawn` / `destroy` an agent by VMID |
| `provider.tf` | bpg/proxmox provider (endpoint + token from env) |
| `backend.tf.template` | Optional HTTP (GitLab) state backend |

## Setup

1. Build an agent LXC template and note its VMID (set `AS_TEMPLATE_VMID`).
2. Export the environment (never commit values):

```bash
export PVE_USER='root@pam'
export PVE_TOKEN_NAME='flashpoint'
export PVE_TOKEN_VALUE='…'
export PVE_HOST='pve.example.com'
export PVE_NODE='pve'
export AS_TEMPLATE_VMID=8000
export AS_PGVECTOR_WRITER_PASS='…'
export AS_GITLAB_URL='https://gitlab.example.com'
export AS_GITLAB_PROJECT_ID='2'
export AS_GITLAB_TOKEN='…'
```

## Use

```bash
./spawn-agent.sh spawn 8001 10.0.0.10 ephemeral "analyse Q1 receipts"
./spawn-agent.sh destroy 8001
```

Terraform state for each agent is stored under `agents/<vmid>/` and (if the
backend is enabled) in your GitLab project's Terraform state. Destroying an
agent removes the container but its decisions persist in the decisions DB.
