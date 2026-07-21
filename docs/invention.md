# Flashpoint — Invention Pipeline (frog-leap ideation + adversarial backtesting)

Generate many domain-collision ideas, backtest them adversarially with **sourced**
prior-art research, and surface the survivors as candidates for new inventions,
concepts or patents. This is Flashpoint's simulation/search pattern pointed at
invention: the work is embarrassingly parallel, and every idea carries a
traceable id and a full reasoning trail in the decisions DB.

> **Read-only and offline by design.** The pipeline only reads public prior art
> and writes to the decisions DB. It never files, posts, emails or discloses
> anything. Patent strategy (what to disclose, when, defend-vs-publish) is a
> human/legal decision, not the pipeline's.

## The funnel

```
generate 100 ideas (cheap)          structured randomness: collide 2+ domains
  → screen (cheap)                  harsh kill-pass on novelty/feasibility/value
  → RESEARCH GATE (sourced)         real prior-art/scholar/web search per survivor
  → deep backtest (heavy)           hostile examiner attacks it using the dossier
  → reverse-engineer + rank         defensible kernel + buildable path
```

Only a few ideas should survive. That is the point: the system is built to *kill*
weak ideas with evidence, not to flatter them.

## Why "structured randomness", not "100 random ideas"

Pure random ideation is mostly noise. Novelty actually lives at the *collision of
domains you understand deeply*. `invention/seeds.yaml` holds your real domain
inventory (governed AI workforce, property/lettings, construction/snagging, BMS,
self-hosted infra, institutional memory, finance ops, …) plus a set of constraint
inversions ("what if it were free / under a second / provable to an auditor").
The generator collides 2+ domains and applies an inversion, so ideas are bold but
grounded in your unfair advantage.

## The research gate (what makes "novel" mean something)

Without research, "novel" is an opinion. Each survivor gets a **sourced dossier**
before backtesting, built by `invention/research_tools.py`:

1. **Decompose** the idea into 2–3 core *mechanism* noun-phrases (the actual
   mechanism, not the marketing name).
2. **Search each mechanism** across real sources with synonym expansion:
   - arXiv (scholarly prior art, keyless)
   - Semantic Scholar (academic search, keyless, throttled + retried)
   - Tavily web search (product/patent-adjacent prior art, needs `TAVILY_API_KEY`)
3. **Assemble a dossier** — closest prior art with links + a coarse prior-art
   density signal — which is logged for provenance and fed to the backtest agent.

The backtest agent then argues *from those citations*, not from the model's stale
memory. This is the difference between triage and theatre. **Caveat:** agents
clear obvious prior art and surface candidates; they do not *certify* novelty.
That final legal judgement belongs to a patent attorney/professional searcher.
The output is "research-triaged candidates with sourced dossiers".

## Run it

```bash
export OPENROUTER_API_KEY=...   # LLM for generate/screen/backtest
export TAVILY_API_KEY=...       # web prior-art search (optional but recommended)

python3 -m invention.pipeline \
  --ideas 100 --survivors 10 \
  --gen-model openai/gpt-5.6-sol \
  --deep-model openai/gpt-5.6-sol \
  --out /tmp/invention-run
```

- `--ideas` — how many ideas to generate (cheap model)
- `--survivors` — how many go through research + deep backtest (the funnel top)
- `--gen-model` / `--deep-model` — cheap vs heavy; spend heavy tokens only on
  survivors. Defaults are your fleet default; swap to Haiku/Opus as you like.
- Results: ranked candidates written to `--out/results.json` and printed.

A good first run is small (`--ideas 12 --survivors 4`) to judge output quality
before scaling to 100.

## Output

Each candidate carries: the idea, its screen scores, the sourced research dossier
(closest prior art + links), and the backtest verdict — novelty / feasibility /
value scores, closest prior art, the delta, any fatal flaw, and (for survivors)
the defensible kernel and buildable path. Everything is keyed by the idea's id so
you can trace the full reasoning chain.

## Scaling it (Flashpoint / Temporal)

The local runner works with zero infra. For 100+ ideas, fan the stages out as
Flashpoint spawned agents or a Temporal wave (`flashpoint_temporal/`): one agent
per idea for generation/screening, then one heavy agent per survivor for research
+ backtest, durable and idempotent. The decisions DB holds the per-idea audit
trail either way.

## Tuning

- **Screener too harsh/lenient?** Edit the rubric in `screen_ideas`
  (`invention/pipeline.py`) — it currently kills anything not clearly new.
- **Different flavour of ideas?** Edit `invention/seeds.yaml` (domains +
  constraints). This is the single biggest lever on output quality.
- **Better prior art?** Add a dedicated patent API (Google Patents / Espacenet /
  USPTO) to `research_tools.py` alongside arXiv/S2/Tavily for a stronger
  patent-specific gate.
