# Flashpoint — Use Cases & Examples

Flashpoint is built for **embarrassingly parallel** work: any task where you can
give the same (or a templated) instruction to thousands of independent agents at
once. This page shows the patterns with concrete, runnable examples. Each one
uses the intake paths already in the repo (`intake/`, `flashpoint_temporal/`,
`POST /spawn`, `POST /spawn_batch`).

The rule of thumb: if the work splits into independent units that don't need to
talk to each other mid-task, it's a Flashpoint wave. If the units must
coordinate, use a small orchestrated crew instead.

---

## 1. Estate-scale audits (read-only, safe to run unattended)

Give every host, container or service its own agent and have each report health
and anomalies to the decision log. What used to be a week of manual checks runs
as one wave.

**manifest (`estate-audit.json`)** — one agent per system:

```json
[
  {"agent_id": "audit-espo",      "tier": "ephemeral", "mission": "Read the EspoCRM health endpoint and report status, version and any errors to the decision log."},
  {"agent_id": "audit-pve0",      "tier": "ephemeral", "mission": "List LXC/VM guests on Proxmox host pve0 and report any stopped-but-onboot guests or >90% disk usage."},
  {"agent_id": "audit-airflow",   "tier": "ephemeral", "mission": "List Airflow DAGs and report any that are paused, failing, or have not run in 7+ days."},
  {"agent_id": "audit-gitlab",    "tier": "ephemeral", "mission": "Check GitLab health and report version, storage use and any failed background jobs."},
  {"agent_id": "audit-dns-ssl",   "tier": "standard",  "mission": "For each domain in the list, check DNS resolution and TLS certificate expiry; flag anything expiring in <30 days."}
]
```

```bash
python3 intake/flashpoint_intake.py \
  --spawners http://runner1:2880,http://runner2:2880 \
  --manifest estate-audit.json --batch nightly-audit
```

**Why Flashpoint fits:** 500 independent checks, each traceable, all in parallel,
results searchable afterwards. Run it on a nightly Temporal schedule for a
continuous "estate intelligence" briefing.

---

## 2. Documents at volume

Summarise, extract, or classify thousands of documents — one agent per document,
results into pgvector for semantic search.

**CSV (`docs.csv`)**:

```csv
mission,tier,agent_id
"Summarise document id=1001 and extract parties, dates and monetary values",ephemeral,doc-1001
"Summarise document id=1002 and extract parties, dates and monetary values",ephemeral,doc-1002
"Summarise document id=1003 and extract parties, dates and monetary values",ephemeral,doc-1003
```

```bash
python3 intake/flashpoint_intake.py \
  --spawners http://runner1:2880 \
  --csv docs.csv --batch doc-summaries-q1
```

**Why Flashpoint fits:** each document is independent; the per-document agent_id
doubles as the traceability key back to the source record.

---

## 3. Parallel research / OSINT / diligence

One agent per subject (company, person, property), each pulling from its sources
and returning a structured brief.

```bash
# Let an agent author the variants from one base mission, then spawn them all.
python3 intake/flashpoint_intake.py \
  --spawners http://runner1:2880 \
  --generate "Produce a due-diligence brief on a UK company: Companies House status, directors, charges, and any adverse media" \
  --variants 40 --batch diligence-batch-7
```

**Why Flashpoint fits:** the *variant-generation* pathway means you describe the
goal once and Flashpoint fans it out; each subject stays independent and
traceable.

---

## 4. Same change across many repos

One agent per repository, each applying the same migration and opening its own
PR. (Keep write access behind review — see the security note.)

```json
[
  {"agent_id": "repo-api",   "tier": "standard", "mission": "In repo api-service, bump the base image to python:3.13-slim, run the test suite, and open a PR with the results."},
  {"agent_id": "repo-web",   "tier": "standard", "mission": "In repo web-frontend, bump the base image to python:3.13-slim, run the test suite, and open a PR with the results."},
  {"agent_id": "repo-worker","tier": "standard", "mission": "In repo worker, bump the base image to python:3.13-slim, run the test suite, and open a PR with the results."}
]
```

**Why Flashpoint fits:** the work is identical per repo but independent; a single
wave replaces a tedious manual sweep. Temporal gives you per-repo retry and a
clean audit of which repos succeeded.

---

## 5. Massive simulation / search

Thousands of agents each explore a different parameter or strategy; the best
result wins. Classic Monte-Carlo / grid-search shape.

```json
[
  {"agent_id": "sim-lr-0.001", "tier": "ephemeral", "mission": "Run the backtest with learning_rate=0.001 and report Sharpe ratio and max drawdown to the decision log."},
  {"agent_id": "sim-lr-0.01",  "tier": "ephemeral", "mission": "Run the backtest with learning_rate=0.01 and report Sharpe ratio and max drawdown to the decision log."},
  {"agent_id": "sim-lr-0.1",   "tier": "ephemeral", "mission": "Run the backtest with learning_rate=0.1 and report Sharpe ratio and max drawdown to the decision log."}
]
```

Query the decision log afterwards to rank the parameter set:

```sql
SELECT agent_id, decision, confidence, tags
FROM agent_decisions
WHERE agent_id LIKE 'sim-%'
ORDER BY confidence DESC;
```

**Why Flashpoint fits:** thousands of independent trials, each tagged so you can
trace the winning run back to its exact parameters.

---

## 6. Durable production wave (Temporal)

The same patterns, but with Temporal's durability, idempotency and rate-limiting
for long or expensive waves. Use this when a wave must survive a crashed worker
and never double-spawn.

```bash
# worker (long-lived)
export TEMPORAL_ADDRESS=<temporal-host>:7233
export FP_SPAWNER=http://runner1:2880
python3 -m flashpoint_temporal.worker

# start the wave (durable)
export OPENROUTER_API_KEY=...
python3 -m flashpoint_temporal.start_wave \
  --manifest estate-audit.json --wave nightly-audit --max-concurrent 32
```

Watch per-agent spawn/await/destroy live in the Temporal UI; a failure replays
to the exact agent that failed.

---

## Choosing the right pattern

| If the work is… | Use | Example |
|---|---|---|
| Read-only, recurring, many targets | Scheduled audit wave | §1 |
| Many independent documents/records | Manifest/CSV batch | §2 |
| A goal but not the variants | Agent-generated intake | §3 |
| Same change, many repos/hosts | Batch + PR review gate | §4 |
| Many parameter trials | Simulation wave + decision query | §5 |
| Long/expensive, must not lose state | Temporal wave | §6 |

## Stay safe at scale

- The ceiling is **LLM cost and rate limits**, not the spawner. Prefer many
  cheap fast agents (Haiku-ephemeral) over a few expensive ones; throttle with
  `max_concurrent` / `--max-parallel`. See `docs/scaling.md`.
- For waves that read **untrusted content** (web, email, uploads), keep them
  read-only or put writes behind a human approval step.
- Give every wave a meaningful `batch`/`wave` id and per-agent `agent_id` — that
  is what makes the results auditable afterwards.
