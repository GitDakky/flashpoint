# Flashpoint Temporal

Durable, traceable agent waves on Temporal. Temporal is the orchestration brain
(durability, retry, rate-limiting, real-time visibility); the Flashpoint spawner
is the ignition muscle (fast container spawn/teardown). The spawner stays
untouched — Temporal wraps it.

## Why Temporal and not Airflow

Flashpoint is an event-driven, high-throughput, spawn-and-destroy system, not a
scheduled batch pipeline. Airflow's DAG scheduler is built for "run this ETL at
2am"; it chokes on hundreds of thousands of dynamic, sub-second tasks. Temporal
is built for exactly this: durable execution of code that takes milliseconds or
months, with dynamic fan-out, per-entity workflow IDs, signals, and a UI that
stays usable at scale. See the project README for the full comparison.

## What this gives you over the plain intake CLI

- **Durability** — a crashed worker replays to the exact agent that failed and
  resumes; the wave is never lost.
- **Idempotency** — `agent_id` is the idempotency key, so a Temporal retry never
  double-spawns an agent.
- **Rate limiting** — a concurrency semaphore throttles the wave to respect model
  API limits (the real ceiling at scale).
- **Guaranteed teardown** — every agent is destroyed in a `finally`, so retries
  and timeouts don't leak containers.
- **Real-time visibility** — the Temporal UI shows per-agent spawn/await/destroy
  state across the whole wave.

## Layout

| File | Role |
|---|---|
| `activities.py` | `spawn_agent`, `await_agent`, `destroy_agent` — thin idempotent wrappers over the Spawner API |
| `workflows.py` | `AgentWaveWorkflow` — fans a wave out to per-agent spawn → await → destroy |
| `worker.py` | Temporal worker registering the workflow + activities |
| `start_wave.py` | Reads a manifest and starts an `AgentWaveWorkflow` |
| `requirements.txt` | `temporalio` (the core spawner stays stdlib-only) |

## Run it

```bash
pip install -r flashpoint_temporal/requirements.txt

# worker (long-lived)
export TEMPORAL_ADDRESS=<temporal-host>:7233
export TEMPORAL_NAMESPACE=default
export TEMPORAL_TASK_QUEUE=flashpoint
export FP_SPAWNER=http://<spawner-host>:2880
python3 -m flashpoint_temporal.worker

# start a wave (separate shell)
export OPENROUTER_API_KEY=...
python3 -m flashpoint_temporal.start_wave \
  --manifest intake/missions.example.json --wave wave-1 --max-concurrent 32
```

`start_wave.py` reads the same manifest format as `intake/` (JSON list or JSONL)
and assigns deterministic `agent_id`s. The wave result is a per-agent summary
(agent_id, ok, outcome, gateway_url, error).

## systemd (optional)

`flashpoint-temporal.service` runs the worker under systemd. Point
`Environment=` lines at your Temporal and spawner, then
`systemctl enable --now flashpoint-temporal`.
