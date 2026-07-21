"""Flashpoint Temporal worker — registers activities and the wave workflow.

Run:
  export TEMPORAL_ADDRESS=localhost:7233
  export TEMPORAL_NAMESPACE=default
  export TEMPORAL_TASK_QUEUE=flashpoint
  export FP_SPAWNER=http://<spawner-host>:2880
  python3 -m flashpoint_temporal.worker
"""
from __future__ import annotations

import asyncio
import os

from temporalio.client import Client
from temporalio.worker import Worker

from .activities import await_agent, destroy_agent, spawn_agent
from .workflows import AgentWaveWorkflow

TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
TEMPORAL_NAMESPACE = os.environ.get("TEMPORAL_NAMESPACE", "default")
TASK_QUEUE = os.environ.get("TEMPORAL_TASK_QUEUE", "flashpoint")


async def main() -> None:
    client = await Client.connect(TEMPORAL_ADDRESS, namespace=TEMPORAL_NAMESPACE)
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[AgentWaveWorkflow],
        activities=[spawn_agent, await_agent, destroy_agent],
    )
    print(f"Flashpoint Temporal worker listening on task queue '{TASK_QUEUE}' "
          f"({TEMPORAL_ADDRESS}, ns={TEMPORAL_NAMESPACE})")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
