# Flashpoint — Hands-off Deployment Prompt for Agentic Systems

This file contains a self-contained prompt you can hand to an agentic system
(Hermes Agent, OpenClaw, or any capable agent runtime) so it deploys Flashpoint
end-to-end with **no human involvement** beyond supplying two secrets and
answering "go".

Copy everything inside the fenced block below and give it to the agent. Fill in
the four `<PLACEHOLDER>` values first (or tell the agent to ask you for them).

---

```text
You are an autonomous deployment agent. Deploy Flashpoint — an ephemeral
AI-agent spawner — on a target Docker host, end to end, without pausing for
confirmation except where explicitly told to. Work idempotently: every step must
be safe to re-run. Report a short, factual summary at the end (what you did,
what is running, how to use it, anything that needs a human). Do not invent
outputs; if a step fails, diagnose and either fix it or stop and say exactly
why.

## Context you need (fill these in or ask me once, up front)
- TARGET_HOST: SSH address of the Docker host to become a Flashpoint runner
    (e.g. root@203.0.113.10). I must already have SSH key access.
- GATEWAY_IP: the IP address other hosts will use to reach this runner's agent
    gateways (usually the host's own primary IP, e.g. 203.0.113.10).
- OPENROUTER_API_KEY: the LLM key the spawned agents will use (secret — handle
    it as a secret; never print it, never commit it).
- TEMPORAL (optional): address of a Temporal server as host:7233 if you want
    durable waves. If I say "skip Temporal", deploy only the spawner.

## Rules
- British English in anything you write for me.
- Do not commit or print secrets. Write them only to mode-0600 files.
- Prefer small, verifiable steps. Verify each stage before moving on.
- Do not destroy or restart anything that is already running and healthy.
- If a port, service, or directory already exists and is healthy, reuse it —
  do not blindly recreate.

## Step 1 — Preflight (read-only)
- Confirm SSH works: run a trivial command on TARGET_HOST.
- Confirm Docker is present and the daemon is up (`docker info`). If Docker is
  missing on a Debian/Ubuntu host, install `docker.io` and enable it; otherwise
  stop and tell me Docker is required.
- Confirm Python 3.9+ is present.
- Report host CPU, RAM, and free disk. Recommend the agent density (RAM / 2 GB
  per ephemeral agent) but do not change anything yet.

## Step 2 — Get the code
- Clone https://github.com/GitDakky/flashpoint to /opt/flashpoint-src (or pull if
  it already exists). Use the default branch. If the repo is private and you
  have no credentials, stop and ask me for a read credential — do not work
  around it.

## Step 3 — Build and configure
- Build the agent image: `docker build -t flashpoint/agent:latest agent/` from
  the repo root.
- Create /opt/flashpoint and copy `spawner/spawner.py` into it.
- Write /opt/flashpoint/.env (mode 0600) with:
    FP_SPAWNER_PORT=2880
    FP_AGENT_IMAGE=flashpoint/agent:latest
    FP_GATEWAY_HOST=<GATEWAY_IP>
    FP_REGISTRY_PATH=/var/lib/flashpoint/registry.jsonl
    FP_DEFAULT_MODEL=openrouter/anthropic/claude-opus-4-8
  Create /var/lib/flashpoint. Do NOT put OPENROUTER_API_KEY in this file; the
  key is passed per-spawn, not stored on the runner.

## Step 4 — Run the spawner
- Install `spawner/as-spawner.service` to systemd, `daemon-reload`, then
  `systemctl enable --now as-spawner` and `systemctl restart as-spawner`.
- Health-check: `curl -fsS http://127.0.0.1:2880/health` must return
  `{"status":"ok",...}`. If it does not, inspect `systemctl status as-spawner`
  and the process output, fix the cause, and re-check before continuing.

## Step 5 — Smoke test (prove it end to end)
- Spawn one ephemeral agent via the API with a trivial mission
  (e.g. "reply with FLASHPOINT_OK then exit") and pass OPENROUTER_API_KEY in the
  spawn body's `openrouter_key` field (do not log the key).
- Poll `/agents` until the agent appears, confirm its gateway responds, then
  DELETE `/agent/<id>` and confirm it is gone.
- Record spawn and destroy timings.

## Step 6 — Optional: Temporal worker (only if I gave you a TEMPORAL address)
- `pip install -r flashpoint_temporal/requirements.txt`.
- Install `flashpoint_temporal/flashpoint-temporal.service` with
  TEMPORAL_ADDRESS set to the address I gave, FP_SPAWNER pointing at this
  runner, and OPENROUTER_API_KEY in the unit's Environment (0600). Enable and
  start it, then confirm the worker registers on the `flashpoint` task queue.
- Start a 3-agent smoke wave with `flashpoint_temporal/start_wave.py` against a
  tiny manifest and confirm all three agents succeed.

## Step 7 — Handover summary
Report, tersely:
- Runner host, spawner URL (http://GATEWAY_IP:2880), and health status.
- Smoke-test result with spawn/destroy timings.
- Whether the Temporal worker is running (and its task queue) or was skipped.
- The exact curl command to spawn an agent, and the intake command to run a
  batch from a manifest.
- Anything that still needs a human (missing credentials, Temporal not
  reachable, capacity warnings).

Begin with Step 1 now. Ask me only for the four context values if I have not
provided them; otherwise proceed without further questions.
```

---

## How to use this prompt

1. Copy the fenced block above.
2. Fill in `TARGET_HOST`, `GATEWAY_IP`, `OPENROUTER_API_KEY`, and optionally
   `TEMPORAL` — or delete the placeholders and let the agent ask you for them.
3. Paste it into your agentic system (Hermes, OpenClaw, etc.) as the task.
4. The agent deploys Flashpoint hands-off and reports back.

## What "hands-off" means here (and its limits)

The prompt is written so a capable agent can complete every step without a human
in the loop, given SSH access to the target and the two secrets. The only human
touchpoints are: supplying SSH access to the host, supplying the LLM key, and
(optionally) the Temporal address. Everything else — preflight, install, build,
configure, run, smoke-test, handover — is delegated to the agent.

If you want true zero-touch across *many* runners, put this prompt behind a
Temporal/CI driver: one orchestrator runs the prompt against a list of
`TARGET_HOST`s, and Flashpoint effectively bootstraps its own fleet.
