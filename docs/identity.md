# Flashpoint — Identity & Traceability

Every agent spawned by Flashpoint gets a **unique, traceable identity**. This is
the property that lets you run 100 M agents and still answer, for any one of
them, *"which exact spawn produced this agent, with what mission, at what time?"*

## The agent id

- Format: `fp-<12 hex chars>` (e.g. `fp-3f9a1c2b7d4e`), from
  `secrets.token_hex(6)` — 48 bits of entropy per id.
- Collision probability at 100 M concurrent ids (birthday bound) is ~2×10⁻⁶; at
  1 M it is ~2×10⁻⁹. For strict zero-collision at 100 M, either let the caller
  supply `agent_id` (deterministic naming, e.g. `wave-7-agent-00012345`) or widen
  to `token_hex(8)` (64 bits) — a one-line change in `spawner.py`.
- You may always pass your own `agent_id` in the spawn request to embed a
  wave/batch/tenant prefix for downstream traceability.

## The spawn record

`POST /spawn` returns the full identity of the agent it just created:

```json
{
  "agent_id":      "fp-3f9a1c2b7d4e",
  "container_id":  "1a2b3c4d5e6f",
  "tier":          "ephemeral",
  "mission":       "analyse Q1 receipts",
  "gateway_url":   "http://<host>:32770",
  "gateway_token": "…",
  "model":         "openrouter/anthropic/claude-opus-4-8",
  "metadata":      {"wave": "7", "tenant": "finance"},
  "status":        "starting",
  "spawned_at":    "2026-07-21T16:43:00+00:00"
}
```

`agent_id` is the traceability anchor. The same value is carried as:
- the Docker container name and hostname
- the `fp.agent_id` container label
- the `AS_AGENT_ID` env var inside the agent (used by the decision logger)
- the key in the spawn registry (below)

`metadata` is an optional caller-supplied object echoed back verbatim — use it
to tag an agent with the wave, batch, tenant or upstream job it belongs to.

## The spawn registry (survives teardown)

Set `FP_REGISTRY_PATH` and the spawner appends one JSON line per spawn and per
destroy to a local registry file. Because the registry outlives the container,
an `agent_id` can be traced back to its exact spawn even after the agent is gone:

```
GET /agent/fp-3f9a1c2b7d4e
```

returns the stored spawn record (or live container state if the registry is
disabled and the agent is still running). For a real multi-host deployment,
point each spawner's registry at shared storage (or swap the JSONL writer for a
Postgres insert) so ids resolve fleet-wide from any node.

## Decision-log linkage

Each agent writes decisions to the decisions DB keyed by `agent_id`
(`AS_AGENT_ID`). Query by id to recover everything the agent decided, after the
container has been destroyed:

```sql
SELECT * FROM agent_decisions WHERE agent_id = 'fp-3f9a1c2b7d4e' ORDER BY timestamp;
```

So the chain is complete and auditable:

`agent_id → spawn record (registry) → live container (label) → decisions (DB)`
