"""Flashpoint invention pipeline — generate -> screen -> research -> backtest -> rank.

Runs the funnel locally (direct LLM calls) by default so it works with zero
infra; the same stages map onto Flashpoint spawned agents / Temporal for scale.

Read-only and offline by design: agents read public prior art and write to the
decisions DB; nothing is filed, posted or sent.

Usage:
  python3 -m invention.pipeline --ideas 12 --survivors 4 \
      --gen-model openrouter/anthropic/claude-haiku-4-5 \
      --deep-model openrouter/anthropic/claude-opus-4-8 \
      --out /tmp/invention-run
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import research_tools

HERE = Path(__file__).parent
SEEDS = HERE / "seeds.yaml"


# ----------------------------------------------------------------- LLM call --
def llm(prompt, model, key, max_tokens=2000, base="https://openrouter.ai/api/v1"):
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"LLM {model} HTTP {e.code}: {detail}") from e
    return data["choices"][0]["message"]["content"]


def _json_array(text):
    """Extract the first JSON array from an LLM response, tolerantly (fences ok)."""
    text = re.sub(r"```(?:json)?", "", text)
    start = text.find("[")
    if start == -1:
        return []
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except Exception:
                    return []
    return []


def _json_object(text):
    text = re.sub(r"```(?:json)?", "", text)
    start = text.find("{")
    if start == -1:
        return {}
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except Exception:
                    return {}
    return {}


# ------------------------------------------------------------------- seeds --
def load_seeds(path=SEEDS):
    """Minimal YAML read (domains + constraints) without a yaml dependency."""
    domains, constraints, section = [], [], None
    for raw in Path(path).read_text().splitlines():
        line = raw.rstrip()
        s = line.strip()
        if s.startswith("domains:"):
            section = "d"; continue
        if s.startswith("constraints:"):
            section = "c"; continue
        if s.startswith("- "):
            item = s[2:].strip()
            (domains if section == "d" else constraints if section == "c" else []).append(item)
    return domains, constraints


def _retry(fn, attempts=4, base_delay=2.0):
    """Retry a stage call on transient network errors AND transient provider
    4xx/5xx (the model route is intermittently flaky)."""
    delay = base_delay
    for i in range(attempts):
        try:
            return fn()
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
            if i == attempts - 1:
                raise
            time.sleep(delay); delay *= 2
        except RuntimeError as e:
            # llm() raises RuntimeError for HTTP errors; retry transient ones.
            msg = str(e)
            transient = any(c in msg for c in ("HTTP 400", "HTTP 408", "HTTP 409", "HTTP 425", "HTTP 429", "HTTP 5"))
            if not transient or i == attempts - 1:
                raise
            time.sleep(delay); delay *= 2


# ------------------------------------------------------------------ stages --
def generate_ideas(n, domains, constraints, model, key):
    """Generate n domain-collision ideas. Structured randomness, not pure noise."""
    ideas = []
    per_call = 10
    random.seed()
    while len(ideas) < n:
        d = random.sample(domains, min(4, len(domains)))
        c = random.sample(constraints, min(2, len(constraints)))
        prompt = (
            "You are an inventive engineer who thinks in MECHANISMS, not business outcomes. "
            f"Generate {per_call} genuinely novel invention concepts by COLLIDING 2+ of these domains "
            "and applying a constraint inversion.\n\n"
            f"Domains to draw from (collide 2+ per idea):\n- " + "\n- ".join(d) + "\n\n"
            f"Constraint inversions to apply:\n- " + "\n- ".join(c) + "\n\n"
            "For EACH idea you MUST supply a concrete, named technical mechanism — a specific "
            "protocol, algorithm, data structure, or architectural primitive — that does not "
            "obviously exist. AVOID 'desired outcome' ideas (e.g. 'a dashboard that shows X', "
            "'automatically reconciles Y'); those are not patentable and will be rejected.\n"
            "Rules for each idea:\n"
            "- Sit at the intersection of at least two domains above (not generic).\n"
            "- Title + one-line description.\n"
            "- 'mechanism': the specific novel protocol/algorithm/primitive, named and described "
            "  in one sentence (e.g. 'a canonical request-fingerprint that binds X to Y').\n"
            "- 'non_obvious': one sentence on WHY this is not a predictable aggregation of known "
            "  parts (the actual inventive step).\n"
            "- 'mechanisms': 2-3 mechanism noun-phrases usable for prior-art search.\n\n"
            'Return ONLY a JSON array of {{"title","description","mechanism","non_obvious",'
            f'"mechanisms":["...",...]}} objects, exactly {per_call} of them. No prose, no markdown.'
        )
        try:
            arr = _retry(lambda: _json_array(llm(prompt, model, key, max_tokens=3000))) or []
            for item in arr:
                if isinstance(item, dict) and item.get("title") and item.get("mechanisms"):
                    desc = (item.get("description") or "").strip()
                    mech = (item.get("mechanism") or "").strip()
                    nonob = (item.get("non_obvious") or "").strip()
                    ideas.append({
                        "id": f"idea-{len(ideas)+1:03d}",
                        "title": item["title"].strip(),
                        "description": desc,
                        "mechanism": mech,
                        "non_obvious": nonob,
                        "mechanisms": [str(m).strip() for m in item["mechanisms"][:3]],
                    })
        except Exception as e:
            print(f"  generate batch error: {e}", file=sys.stderr)
        time.sleep(0.5)
    return ideas[:n]


def screen_ideas(ideas, model, key, keep_top=None, min_score=0):
    """Cheap scoring pass. Scores every idea, then keeps the top `keep_top` by
    combined score (and any scoring >= min_score). A rank-and-keep funnel, not a
    hard kill, so the research gate always has material to work on."""
    for idea in ideas:
        prompt = (
            "You are a sceptical technical reviewer. Score this invention idea 0-10 on each of "
            "novelty, feasibility, value (10 = best). Reward concrete novel mechanisms; penalise "
            "'desired outcome' ideas with no enabling mechanism. Be honest; most ideas are only partly new.\n\n"
            f"Title: {idea['title']}\nDescription: {idea['description']}\n"
            f"Mechanism: {idea.get('mechanism','')}\nNon-obvious step: {idea.get('non_obvious','')}\n"
            f"Search phrases: {', '.join(idea['mechanisms'])}\n\n"
            'Return ONLY a JSON object {"novelty":int,"feasibility":int,"value":int,'
            '"reason":"one sentence"}.'
        )
        try:
            o = _retry(lambda: _json_object(llm(prompt, model, key, max_tokens=300))) or {}
            idea["screen"] = o
            idea["screen_score"] = sum(int(o.get(k, 0) or 0) for k in ("novelty", "feasibility", "value"))
        except Exception as e:
            print(f"  screen error {idea['id']}: {e}", file=sys.stderr)
            idea["screen_score"] = 0
        time.sleep(0.3)
    ranked = sorted(ideas, key=lambda x: x.get("screen_score", 0), reverse=True)
    if keep_top is not None:
        kept = [i for i in ranked[:keep_top] if i.get("screen_score", 0) >= min_score]
        return kept
    return [i for i in ranked if i.get("screen_score", 0) >= min_score]


def research_ideas(ideas):
    """Attach a sourced novelty dossier to each idea (real API research)."""
    for idea in ideas:
        try:
            dossier = research_tools.build_dossier(idea["title"], idea["mechanisms"])
            idea["dossier"] = dossier
            idea["dossier_text"] = research_tools.dossier_to_text(dossier)
        except Exception as e:
            print(f"  research error {idea['id']}: {e}", file=sys.stderr)
            idea["dossier"] = None
            idea["dossier_text"] = "(research failed)"
    return ideas


def backtest_ideas(ideas, model, key):
    """Deep adversarial backtest, grounded in the sourced dossier. Heavy model."""
    for idea in ideas:
        prompt = (
            "You are a hostile patent examiner and technical diligence expert. Attack this "
            "invention idea using the RESEARCH DOSSIER provided (real prior art and sources). "
            "Your job is to kill it if you can.\n\n"
            f"IDEA\nTitle: {idea['title']}\nDescription: {idea['description']}\n"
            f"Mechanism: {idea.get('mechanism','')}\nClaimed non-obvious step: {idea.get('non_obvious','')}\n"
            f"Search phrases: {', '.join(idea['mechanisms'])}\n\n"
            f"{idea.get('dossier_text','(no dossier)')}\n\n"
            "Assess rigorously:\n"
            "1. NOVELTY: from the dossier's closest prior art, is the specific novel kernel "
            "   already disclosed? Name the closest source and the delta.\n"
            "2. FEASIBILITY: can it be built with real, current components?\n"
            "3. VALUE: who pays, why, and why hasn't the market solved it?\n"
            "4. REVERSE-ENGINEER: if it survives, the minimum buildable path and the defensible "
            "   kernel worth protecting.\n\n"
            'Return ONLY a JSON object {"novelty":int,"feasibility":int,"value":int,'
            '"closest_prior_art":"...","delta":"...","fatal_flaw":"... or null",'
            '"survives":true|false,"defensible_kernel":"...","verdict_reason":"..."} '
            "(ints 0-10)."
        )
        try:
            idea["backtest"] = _retry(lambda: _json_object(llm(prompt, model, key, max_tokens=1500))) or {"survives": False, "error": "empty"}
        except Exception as e:
            print(f"  backtest error {idea['id']}: {e}", file=sys.stderr)
            idea["backtest"] = {"survives": False, "error": str(e)}
        time.sleep(0.5)
    return ideas


def rank(ideas):
    def score(x):
        b = x.get("backtest", {})
        s = sum(int(b.get(k, 0) or 0) for k in ("novelty", "feasibility", "value"))
        return s + (10 if b.get("survives") else 0)
    return sorted(ideas, key=score, reverse=True)


# --------------------------------------------------------------------- run --
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ideas", type=int, default=12)
    ap.add_argument("--survivors", type=int, default=4)
    ap.add_argument("--gen-model", default="openai/gpt-5.6-sol")
    ap.add_argument("--deep-model", default="openai/gpt-5.6-sol")
    ap.add_argument("--out", default="/tmp/invention-run")
    ap.add_argument("--seeds", default=str(SEEDS))
    args = ap.parse_args()

    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        sys.exit("OPENROUTER_API_KEY not set")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    domains, constraints = load_seeds(args.seeds)
    print(f"seeds: {len(domains)} domains, {len(constraints)} constraints")

    print(f"\n[1/4] generating {args.ideas} ideas ({args.gen_model}) ...")
    ideas = generate_ideas(args.ideas, domains, constraints, args.gen_model, key)
    print(f"  generated {len(ideas)}")

    print(f"\n[2/4] screening ({args.gen_model}) ...")
    survivors = screen_ideas(ideas, args.gen_model, key, keep_top=max(args.survivors, 1))
    print(f"  survivors: {len(survivors)}")
    for s in survivors:
        print(f"    + {s['id']} {s['title']} (screen {s.get('screen_score')})")

    print(f"\n[3/4] research gate (real prior-art APIs) ...")
    survivors = research_ideas(survivors)

    print(f"\n[4/4] deep backtest ({args.deep_model}) ...")
    survivors = backtest_ideas(survivors, args.deep_model, key)

    ranked = rank(survivors)
    (out / "results.json").write_text(json.dumps(ranked, indent=2))

    print("\n===== RANKED CANDIDATES =====")
    for x in ranked:
        b = x.get("backtest", {})
        flag = "SURVIVES" if b.get("survives") else "killed"
        print(f"\n[{flag}] {x['id']} — {x['title']}")
        print(f"  {x['description']}")
        print(f"  novelty={b.get('novelty')} feasibility={b.get('feasibility')} value={b.get('value')}")
        if b.get("closest_prior_art"):
            print(f"  closest prior art: {b.get('closest_prior_art')}")
        if b.get("delta"):
            print(f"  delta: {b.get('delta')}")
        if b.get("fatal_flaw"):
            print(f"  fatal flaw: {b.get('fatal_flaw')}")
        if b.get("survives") and b.get("defensible_kernel"):
            print(f"  defensible kernel: {b.get('defensible_kernel')}")
    print(f"\nfull results: {out / 'results.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
