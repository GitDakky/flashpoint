"""Flashpoint activities — spawn, await, destroy.

Each activity is a thin, idempotent wrapper around the Flashpoint Spawner API.
Idempotency is anchored on `agent_id`, so a Temporal retry never double-spawns
an agent. The spawner is stateless; all durability lives in Temporal's event
history plus the spawner's spawn registry.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
import urllib.error

from temporalio import activity

SPAWNER = os.environ.get("FP_SPAWNER", "http://127.0.0.1:2880")


def _call(method, path, body=None, timeout=300):
    req = urllib.request.Request(
        SPAWNER + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


@activity.defn
async def spawn_agent(spec: dict) -> dict:
    """Spawn one agent. Idempotent on agent_id: if the agent already exists in
    the spawner registry (e.g. this is a retry), return the existing record
    instead of spawning a duplicate.

    spec keys: agent_id (required), mission, tier, model, soul, user, metadata,
    openrouter_key.
    """
    agent_id = spec.get("agent_id")
    if not agent_id:
        raise ValueError("spec.agent_id is required for idempotent spawn")

    # Idempotency: already spawned?
    status, existing = _call("GET", f"/agent/{agent_id}")
    if status == 200 and existing.get("agent_id"):
        activity.heartbeat(f"{agent_id} already exists")
        return {"ok": True, "reused": True, **existing}

    status, rec = _call("POST", "/spawn", {
        "mission": spec.get("mission", "no mission specified"),
        "tier": spec.get("tier", "ephemeral"),
        "model": spec.get("model"),
        "soul": spec.get("soul"),
        "user": spec.get("user"),
        "agent_id": agent_id,
        "openrouter_key": spec.get("openrouter_key"),
        "metadata": spec.get("metadata") or {},
    })
    if status != 201:
        raise RuntimeError(f"spawn {agent_id} failed ({status}): {rec}")
    return {"ok": True, "reused": False, **rec}


@activity.defn
async def await_agent(payload: dict) -> dict:
    """Wait for an agent to finish its mission.

    Strategy: poll the agent's container status via the spawner. A Flashpoint
    agent exits when its mission completes, so "container gone / Exited" is the
    completion signal. Heartbeats keep the activity alive for long missions.

    payload keys: agent_id (required), timeout_seconds (optional),
    poll_seconds (optional), gateway_url (optional — future: poll the agent
    gateway directly for a richer status than container-liveness).
    """
    agent_id = payload["agent_id"]
    timeout = int(payload.get("timeout_seconds", 3600))
    poll = int(payload.get("poll_seconds", 10))
    deadline = time.time() + timeout

    while time.time() < deadline:
        status, agents = _call("GET", "/agents")
        running = {a["agent_id"]: a for a in agents.get("agents", [])}
        if agent_id not in running:
            return {"ok": True, "agent_id": agent_id, "outcome": "exited"}
        activity.heartbeat(f"{agent_id} running")
        time.sleep(poll)

    # Timed out — surface it so the workflow can decide to destroy/compensate.
    return {"ok": False, "agent_id": agent_id, "outcome": "timeout"}


@activity.defn
async def destroy_agent(agent_id: str) -> dict:
    """Destroy an agent. Idempotent: destroying an already-gone agent is a
    success, so retries are safe."""
    status, rec = _call("DELETE", f"/agent/{agent_id}")
    if status in (200, 404):
        return {"ok": True, "agent_id": agent_id, "destroyed": True}
    raise RuntimeError(f"destroy {agent_id} failed ({status}): {rec}")
