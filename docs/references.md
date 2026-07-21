# Flashpoint — Research Sources & Assumptions

Numbers in `docs/scaling.md` are a model built from the sources below plus values
measured on the live system. Swap in your own measured values as you gather them.

## Measured on the live system (this repo's origin)

| Metric | Value | Context |
|---|---|---|
| Spawn (HTTP → container created) | ~1.3 s | single Docker runner, image pre-pulled |
| Container boot → gateway ready | ~7 s total | OpenClaw gateway `healthz=200` |
| Destroy (HTTP → gone) | ~1.9 s | `docker stop && docker rm` |
| Agent RSS (ephemeral) | ~380 MB | observed live |
| Earlier recorded burst | 10 agents spawned in 1.3 s; 9/10 missions in 8.6 s | architecture notes |

## Isolation technology

| Claim | Source |
|---|---|
| Firecracker boots microVMs in ~125 ms, ~5 MB overhead/VM, up to ~150 microVM/s per host, thousands per machine | firecracker-microvm.github.io; AWS News Blog "Firecracker — Lightweight Virtualization for Serverless Computing"; NSDI'20 paper (Agache et al.) |
| Firecracker VMM starts in ~8 CPU ms; 1 vCPU/128 MiB microVM spec | github.com/firecracker-microvm/firecracker SPECIFICATION.md |
| Practical container density is memory-bound (e.g. ~500 MB/container → ~1000 containers per 512 GB host) | stormbind.net "From 30 to 230 Docker containers per host" + HN discussion; Docker/Kubernetes node guidance |

## Model pricing (per MTok in/out) — July 2026

| Model | Input | Output | Source |
|---|---|---|---|
| Claude Haiku 4.5 | $1.00 | $5.00 | Anthropic pricing via benchlm.ai, cloudzero.com, metacto.com |
| Claude Sonnet 4.6 | $3.00 | $15.00 | as above |
| Claude Opus 4.8 | $5.00 | $25.00 | as above |
| Prompt caching read | 0.1× input | — | morphllm.com Claude Code API cost |
| Batch API | 50% off | 50% off | metacto.com Anthropic pricing |

## Assumptions you should replace with measurements

- Spawn rate per runner: **8 creates/s** (assumed; measure with a parallel-spawn
  test on your runner class).
- Agents per 64 GB runner: **32 ephemeral** (from 2 GB tier cap; real RSS is
  ~380 MB, so there is headroom — but the cap is the safe planning number).
- Tokens per mission: see the tier table in `docs/scaling.md` §2. These are
  planning estimates; instrument a real mission and update.
