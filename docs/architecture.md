# Flashpoint — Architecture

Flashpoint is a two-tier system for spawning large numbers of short-lived AI
task agents on demand and destroying them when their work is done.

## Components

| Component | Role | Lifetime |
|---|---|---|
| Orchestrator | Human/agent-facing. Issues missions to the spawner. | long-lived |
| Spawner API (`spawner/spawner.py`) | HTTP service on a Docker host. Creates/destroys agents. | long-lived |
| Task agents (`agent/`) | Ephemeral containers, one per mission. | seconds–hours |
| Decisions DB (Postgres + pgvector) | Persisted agent decisions, keyed by `agent_id`. | permanent |
| Spawn registry (optional JSONL/Postgres) | Persistent id→spawn mapping, survives teardown. | permanent |

## Flow

```
mission ──► POST /spawn ──► docker run flashpoint/agent
                              │  env: AS_AGENT_ID, AS_MISSION, AS_MODEL, ...
                              ▼
                    agent boots OpenClaw gateway (~5–7 s)
                              │  writes decisions ──► Decisions DB
                              ▼
                    mission complete ──► DELETE /agent/<id> ──► container removed
                                                              └─► registry keeps the id record
```

## Why it is fast

- Agents are plain Docker containers of a pre-built image — no provisioning.
- The image has everything baked in; boot is just starting the gateway.
- Spawn is one `docker run`; destroy is `docker stop && docker rm`. No teardown
  state to reconcile because decisions are written out-of-band to the DB.
- Spawners are stateless and independent, so you shard horizontally: one
  spawner per runner, a queue/router in front, and spawn wall-clock stays ~flat
  as the fleet grows (see `docs/scaling.md`).

## Tiers

| Tier | RAM | vCPU | Use |
|---|---|---|---|
| ephemeral | 2 GB | 1.0 | quick single-shot tasks (the mass-wave default) |
| standard | 3 GB | 2.0 | multi-step projects |
| heavy | 6 GB | 4.0 | coding / pipelines |

## The LXC path (Terraform)

`terraform/` contains the original LXC-clone path: a `proxmox_virtual_environment_container`
module plus `spawn-agent.sh` that clones an LXC agent template and applies
cloud-init. This gives full-OS agents (each with its own LXC, IP and SSH) rather
than Docker containers. It is heavier and slower than the Docker path, and
currently requires the agent LXC template to be rebuilt. Kept for environments
where per-agent OS isolation matters more than raw spawn speed.

## Security note

The spawner currently has **no authentication** and agents run as root inside
their containers. That is acceptable only on a trusted internal network. Before
exposing the API or running untrusted missions, add API auth (mTLS or a bearer
token), run agents as a non-root user, and block agents from reaching the
spawner itself (no recursive spawn). This is deliberately out of scope of this
repo's v1; track it before any production use beyond a private LAN.
