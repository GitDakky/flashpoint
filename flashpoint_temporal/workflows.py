"""Flashpoint Temporal workflow — one durable workflow per agent wave.

A wave is a set of missions to run in parallel. The workflow fans out to
per-agent child units (spawn → await → destroy), each fully retried and
idempotent, and returns a per-agent summary. Temporal's event history makes the
whole wave durable: a crashed worker replays to the exact agent that failed and
resumes, without double-spawning.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
from typing import List, Optional

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from .activities import spawn_agent, await_agent, destroy_agent


@dataclass
class AgentSpec:
    agent_id: str
    mission: str
    tier: str = "ephemeral"
    model: Optional[str] = None
    soul: Optional[str] = None
    user: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    openrouter_key: Optional[str] = None


@dataclass
class AgentResult:
    agent_id: str
    ok: bool
    outcome: str
    gateway_url: Optional[str] = None
    error: Optional[str] = None


@dataclass
class WaveResult:
    wave_id: str
    total: int
    succeeded: int
    failed: int
    results: List[AgentResult] = field(default_factory=list)


@workflow.defn
class AgentWaveWorkflow:
    """Run a wave of Flashpoint agents in parallel, durably.

    Input: dict with keys
      wave_id: str
      agents: [AgentSpec-as-dict, ...]
      max_concurrent: int (optional, default 32) — throttle to respect model
                        API rate limits; the real ceiling at scale.
      mission_timeout_seconds: int (optional, default 3600)
    """

    @workflow.run
    async def run(self, wave: dict) -> dict:
        wave_id = wave.get("wave_id") or workflow.info().workflow_id
        specs = wave.get("agents", [])
        max_concurrent = int(wave.get("max_concurrent", 32))
        timeout_s = int(wave.get("mission_timeout_seconds", 3600))

        retry = RetryPolicy(
            initial_interval=timedelta(seconds=2),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(seconds=30),
            maximum_attempts=3,
        )

        semaphore = asyncio.Semaphore(max_concurrent)
        results: List[AgentResult] = []

        async def run_one(spec: dict) -> AgentResult:
            agent_id = spec["agent_id"]
            async with semaphore:
                try:
                    spawn = await workflow.execute_activity(
                        spawn_agent, spec,
                        start_to_close_timeout=timedelta(seconds=120),
                        retry_policy=retry,
                    )
                    await_res = await workflow.execute_activity(
                        await_agent,
                        {"agent_id": agent_id,
                         "gateway_url": spawn.get("gateway_url"),
                         "timeout_seconds": timeout_s},
                        # Long missions need a long close timeout; heartbeats
                        # keep it alive and detect a dead worker sooner.
                        start_to_close_timeout=timedelta(seconds=timeout_s + 300),
                        heartbeat_timeout=timedelta(seconds=60),
                        retry_policy=retry,
                    )
                    return AgentResult(agent_id=agent_id, ok=await_res.get("ok", False),
                                       outcome=await_res.get("outcome", "unknown"),
                                       gateway_url=spawn.get("gateway_url"))
                except Exception as e:  # noqa: BLE001 — surface per-agent failure, don't sink the wave
                    return AgentResult(agent_id=agent_id, ok=False,
                                       outcome="error", error=str(e))
                finally:
                    # Always attempt teardown; idempotent so retries/timeouts are safe.
                    try:
                        await workflow.execute_activity(
                            destroy_agent, agent_id,
                            start_to_close_timeout=timedelta(seconds=60),
                            retry_policy=retry,
                        )
                    except Exception:  # noqa: BLE001
                        pass

        results = await asyncio.gather(*(run_one(s) for s in specs))
        succeeded = sum(1 for r in results if r.ok)
        return WaveResult(
            wave_id=wave_id,
            total=len(results),
            succeeded=succeeded,
            failed=len(results) - succeeded,
            results=results,
        ).__dict__
