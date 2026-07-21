# Flashpoint — Mission Intake (pushing data in en masse)

Missions and variants get into Flashpoint three ways. All of them end at the
spawner's batch endpoint, which spawns many agents in one call with bounded
parallelism.

## 1. A manifest (JSON / JSONL / CSV)

Pre-populate a file with one entry per agent:

```json
[
  {"mission": "Summarise Q1 receipts", "tier": "ephemeral", "agent_id": "wave-1-agent-00001"},
  {"mission": "Summarise Q2 receipts", "tier": "ephemeral", "agent_id": "wave-1-agent-00002"}
]
```

Push it (sharded across however many spawners you list):

```bash
python3 intake/flashpoint_intake.py \
  --spawners http://10.0.0.5:2880,http://10.0.0.6:2880 \
  --manifest intake/missions.example.json --batch wave-1
```

## 2. A database (missions already in Postgres)

Keep missions in a table and stream them in with a query:

```bash
python3 intake/flashpoint_intake.py \
  --spawners http://10.0.0.5:2880 \
  --from-db "host=db dbname=missions user=ro password=..." \
  --query "SELECT mission_text FROM missions WHERE wave = 7 AND spawned IS NULL" \
  --batch wave-7
```

`--from-db` needs `psycopg2` (`pip install psycopg2-binary`).

## 3. An agent generates the variants (optional pathway)

If you have a base mission but not the variants, let one agent author them:

```bash
python3 intake/flashpoint_intake.py \
  --spawners http://10.0.0.5:2880 \
  --generate "analyse a quarterly financial report and flag anomalies" \
  --variants 25 --batch q1-anomalies
```

The intake spawns a temporary *variant-generator* agent, collects the JSON array
of missions it returns, destroys it, then spawns all 25 variants. (If generation
fails it falls back to mechanical `… (variant N)` suffixes so a run never dies
empty-handed.)

## What happens under the hood

`flashpoint_intake.py` shards your missions across the listed spawners and calls
each spawner's `POST /spawn_batch`:

```json
{
  "batch_id": "wave-1",
  "tier": "ephemeral",
  "spawns": [ {"mission": "...", "agent_id": "..."}, ... ],
  "max_parallel": 8
}
```

The spawner spawns them with bounded parallelism, tags every agent with
`metadata.batch_id`, and returns per-item results. Inspect or tear down the whole
group by batch:

```
GET    /batch/<batch_id>
DELETE /batch/<batch_id>
```

> Batch records are held in the spawner's memory. If you need batches to survive
> a spawner restart, persist them yourself (the spawn registry / decisions DB
> already keeps the per-agent truth).

## Choosing a data path

| Path | Use when | Setup |
|---|---|---|
| Manifest/CSV | one-off bursts, version-controlled mission sets | none — a file |
| Postgres | missions live in a system of record, recurring waves | `psycopg2` |
| Agent-generated | you have the goal but not the variants | one spare agent |

For a true 100 M-agent run you would put a queue (Temporal / RabbitMQ) in front
of `flashpoint_intake.py` so missions stream continuously rather than arriving
as one giant manifest — see `docs/scaling.md`.
