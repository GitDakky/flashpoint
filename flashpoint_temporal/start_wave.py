"""Start a Flashpoint agent wave on Temporal from a manifest.

Reads the same manifest format as intake/ (JSON list or JSONL of spawn objects),
assigns deterministic agent_ids, and starts an AgentWaveWorkflow.

Usage:
  export TEMPORAL_ADDRESS=localhost:7233
  python3 -m flashpoint_temporal.start_wave --manifest intake/missions.example.json \
      --wave wave-1 [--max-concurrent 32] [--tier ephemeral]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from temporalio.client import Client

from .workflows import AgentWaveWorkflow

TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
TEMPORAL_NAMESPACE = os.environ.get("TEMPORAL_NAMESPACE", "default")
TASK_QUEUE = os.environ.get("TEMPORAL_TASK_QUEUE", "flashpoint")


def load_manifest(path: str) -> list:
    text = open(path).read().strip()
    rows = json.loads(text) if text.startswith("[") else [json.loads(l) for l in text.splitlines() if l.strip()]
    agents = []
    for i, row in enumerate(rows):
        if isinstance(row, str):
            row = {"mission": row}
        agents.append({
            "agent_id": row.get("agent_id") or f"{path}-{i:05d}",
            "mission": row.get("mission", "no mission specified"),
            "tier": row.get("tier", "ephemeral"),
            "model": row.get("model"),
            "soul": row.get("soul"),
            "user": row.get("user"),
            "metadata": row.get("metadata") or {},
            "openrouter_key": row.get("openrouter_key") or os.environ.get("OPENROUTER_API_KEY"),
        })
    return agents


async def amain() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--wave", required=True)
    ap.add_argument("--max-concurrent", type=int, default=32)
    ap.add_argument("--tier", default="ephemeral")
    ap.add_argument("--mission-timeout", type=int, default=3600)
    args = ap.parse_args()

    agents = load_manifest(args.manifest)
    for a in agents:
        a["tier"] = a.get("tier") or args.tier
        a["metadata"].setdefault("wave", args.wave)

    client = await Client.connect(TEMPORAL_ADDRESS, namespace=TEMPORAL_NAMESPACE)
    handle = await client.start_workflow(
        AgentWaveWorkflow.run,
        {"wave_id": args.wave, "agents": agents,
         "max_concurrent": args.max_concurrent,
         "mission_timeout_seconds": args.mission_timeout},
        id=f"flashpoint-wave-{args.wave}",
        task_queue=TASK_QUEUE,
    )
    print(f"started wave={args.wave} agents={len(agents)} workflow_id={handle.id}")
    result = await handle.result()
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("failed", 1) == 0 else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(amain()))
