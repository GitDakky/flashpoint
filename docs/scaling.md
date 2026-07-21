# Flashpoint — Scaling to 100,000,000 Agents

This document estimates the compute, spawn-rate and cost needed to run Flashpoint
at scales from 1 agent to 100 million concurrent agents, **with speed as the
priority**. It is a model, not a benchmark: every number is stated with its
assumption so you can swap in real measured values as you gather them.

> **TL;DR** — the compute is the easy part. The hard ceiling at high scale is
> **LLM inference throughput and cost**, not the spawner. Plan for the model API
> first; the runners follow.

---

## 1. The three constraints (in priority order)

| Constraint | What it is | Dominates at |
|---|---|---|
| **LLM inference** | Every agent makes live model calls (tokens in/out). Cost and provider rate limits. | >1,000 agents |
| **Memory on runners** | Each agent holds RAM for its lifetime. Sets agents-per-host. | 1–100,000 agents |
| **Spawn throughput** | Container/microVM creation rate per runner. Sets time-to-full-wave. | all scales (speed) |

Network egress (tokens over the wire) and decision-log writes are negligible
next to these and are noted where relevant.

---

## 2. Per-agent resource assumptions

These match the live tiers in `spawner/spawner.py` and the measured agent
footprint (~380 MB RSS observed for a live agent; tiers set a hard cap above
that). Token estimates are per-agent for a single bounded mission (system prompt
+ mission + tool loop + final answer) — your real missions will differ.

| Tier | RAM cap | vCPU | Est. tokens in | Est. tokens out | Role |
|---|---|---|---|---|---|
| `ephemeral` | 2 GB | 1.0 | ~1,500 | ~500 | quick single-shot tasks |
| `standard`  | 3 GB | 2.0 | ~8,000 | ~3,000 | multi-step projects |
| `heavy`     | 6 GB | 4.0 | ~40,000 | ~15,000 | coding / pipelines |

**Speed-priority choice:** for a fast, huge wave you use `ephemeral`. Smaller RAM
cap = more agents per runner = fewer runners = faster aggregate spawn.

---

## 3. Spawn-rate model (speed priority)

Measured on the current single Docker runner: ~1.3 s spawn-HTTP, gateway ready
~7 s. Spawn throughput is limited by container creation, so **more runners =
more parallel spawns**. Assumed sustainable rate per runner (parallel `docker
run`, image pre-pulled): **~8 creates/sec**. Using faster isolation changes the
constant, not the shape:

| Isolation tech | Boot time | Per-agent overhead | Notes |
|---|---|---|---|
| Docker container (current) | ~1.3 s spawn / ~7 s to gateway | ~380 MB RSS | simplest, default |
| Firecracker microVM | ~125 ms boot | ~5 MB overhead + guest | fastest+most secure, needs KVM + runner agent |
| LXC (Terraform path) | seconds | similar to container | needs template rebuild (currently broken) |

Firecracker is the natural "speed + density" upgrade: ~125 ms boot and ~5 MB
overhead per microVM lets you pack thousands per host. It requires KVM and a
small per-host agent (e.g. ignite / flintlock / a custom VMM driver) instead of
plain Docker — an evolution, not a rewrite, of the spawner.

---

## 4. Compute needed at each scale (ephemeral tier, 2 GB/agent)

Runner sizing assumption: **64 GB runner, ~32 ephemeral agents per runner**
(2 GB each, leaving headroom for the host + spawner). Spawn rate 8/s per runner.
"Time to full wave" is the wall-clock to have every agent created, with all
runners spawning in parallel (the design scales horizontally).

| Agents | Runners (64 GB) | Total agent RAM | Est. time to full wave* |
|---:|---:|---:|---:|
| 1 | 1 | 2 GB | ~0.1 s |
| 100 | 4 | 200 GB | ~3 s |
| 1,000 | 32 | 2 TB | ~4 s |
| 10,000 | 313 | 20 TB | ~4 s |
| 100,000 | 3,125 | 200 TB | ~4 s |
| 1,000,000 | 31,250 | 2 PB | ~4 s |
| 10,000,000 | 312,500 | 20 PB | ~4 s |
| 100,000,000 | 3,125,000 | 200 PB | ~4 s |

\* Time to create all containers across the fleet. Because runners spawn in
parallel, wall-clock stays ~constant as you add runners — this is the whole
point of horizontal sharding. Boot-to-*gateway-ready* adds ~5–7 s per agent,
overlapped across the wave.

**Reading it:** scaling is linear in RAM. 100 M concurrent ephemeral agents need
~200 PB of agent RAM spread over ~3.1 M runners of 64 GB. That is a very large
fleet — this is why, at the top end, you either (a) use Firecracker to cut
per-agent overhead ~70× and shrink hosts, or (b) run agents in **waves** rather
than all 100 M resident at once.

---

## 5. The real ceiling: LLM inference cost

Compute is solvable with money and VMs. The binding constraint is that **every
agent burns tokens**. Cost per agent (and per 1 M / 100 M agents) at current
Anthropic rates, per tier:

| Model | Tier | $/agent | 1,000,000 agents | 100,000,000 agents |
|---|---|---:|---:|---:|
| Haiku 4.5 ($1/$5) | ephemeral | $0.0040 | $4,000 | $400,000 |
| Haiku 4.5 | standard | $0.0230 | $23,000 | $2,300,000 |
| Haiku 4.5 | heavy | $0.1150 | $115,000 | $11,500,000 |
| Sonnet 4.6 ($3/$15) | ephemeral | $0.0120 | $12,000 | $1,200,000 |
| Sonnet 4.6 | standard | $0.0690 | $69,000 | $6,900,000 |
| Sonnet 4.6 | heavy | $0.3450 | $345,000 | $34,500,000 |
| Opus 4.8 ($5/$25) | ephemeral | $0.0200 | $20,000 | $2,000,000 |
| Opus 4.8 | standard | $0.1150 | $115,000 | $11,500,000 |
| Opus 4.8 | heavy | $0.5750 | $575,000 | $57,500,000 |

(Rates: Haiku 4.5 $1/$5, Sonnet 4.6 $3/$15, Opus 4.8 $5/$25 per MTok in/out.
See `docs/references.md` for sources.)

**Takeaways:**
- A 100 M-agent wave of *ephemeral Haiku* agents is **~$400k of inference** —
  feasible as a one-off burst. The same wave on *Opus* is **~$2 M**.
- Provider **rate limits** (requests/sec and tokens/min) will throttle you long
  before 100 M concurrent. You must either reserve enterprise throughput or run
  in waves.
- Prompt caching (90% off repeated input) and the Batch API (50% off) materially
  cut these numbers when missions share context.

---

## 6. Speed-priority recommendations

1. **Use `ephemeral` for the mass wave.** 2 GB cap → 32 agents per 64 GB runner.
2. **Pre-pull the image** on every runner (`docker pull flashpoint/agent:latest`
   at provision time). Pull time is the hidden spawn killer if images are cold.
3. **Shard spawners behind a queue.** One spawner per runner; a router (Temporal
   or RabbitMQ, both already on the estate) fans missions out. This keeps spawn
   wall-clock ~flat as the fleet grows.
4. **Plan waves, not full residency.** For 100 M, run e.g. 100 waves of 1 M
   (≈31 k runners, ~$400k Haiku-ephemeral per wave) rather than 100 M at once.
   You get the same work done with 100× less resident RAM.
5. **Reserve model throughput.** Talk to the provider about enterprise rate
   limits before aiming past ~10 k concurrent agents, or you will queue on the
   API, not on your own infra.
6. **Evaluate Firecracker** if you want the 100 M resident case: ~5 MB overhead
   per agent instead of ~380 MB changes the host economics entirely.

---

## 7. What is NOT the bottleneck

- **Decision-log writes**: one `INSERT` per agent decision; even 100 M rows is
  routine for Postgres with partitioning. Add a writer pool if you exceed ~10 k
  writes/sec sustained.
- **Identity generation**: random hex ids are O(1) and collision-safe at any
  plausible scale (see `docs/identity.md`).
- **Network**: token payloads are KBs; 100 M agents × ~2 KB is ~200 GB of egress
  total — trivial against a datacentre link, and it is the tokens themselves
  (cost), not the bandwidth, that matter.
