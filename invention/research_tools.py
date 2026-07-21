"""Research tools for the Flashpoint invention pipeline.

These run in the pipeline (orchestrator side), NOT inside spawned agents. They
hit real public/search APIs to gather *sourced* evidence about an idea's
novelty, feasibility and value, so the backtest agents argue from citations
rather than the model's stale memory.

Sources:
  - arXiv REST API (scholarly prior art) — keyless
  - Semantic Scholar Graph API (academic search) — keyless, throttled; retried
  - Tavily Search API (web / product / patent-adjacent prior art) — needs
    TAVILY_API_KEY in the environment; degrades gracefully if absent

Everything returns structured, sourced records (title + url + snippet) so the
dossier can be logged with provenance for any later patent review.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

UA = {"User-Agent": "flashpoint-invention/0.1 (research; contact: operator)"}


def _get(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def arxiv_search(query, max_results=5):
    """Scholarly prior art from arXiv. Returns list of {title, id, url, published, summary}."""
    q = urllib.parse.quote(f"all:{query}")
    url = f"https://export.arxiv.org/api/query?search_query={q}&max_results={max_results}&sortBy=relevance"
    out = []
    try:
        root = ET.fromstring(_get(url))
    except Exception:
        return out
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for e in root.findall("a:entry", ns):
        def txt(tag):
            el = e.find(f"a:{tag}", ns)
            return (el.text or "") if el is not None else ""
        t = txt("title").strip().replace("\n", " ")
        i = txt("id").strip()
        p = txt("published")[:10]
        s = txt("summary").strip().replace("\n", " ")
        out.append({"source": "arxiv", "title": t, "id": i.split("/abs/")[-1],
                    "url": i, "published": p, "snippet": s[:400]})
    return out


def semantic_scholar_search(query, max_results=5, retries=3):
    """Academic prior art from Semantic Scholar. Returns list of {title, url, year, citations, snippet}.

    Keyless tier is aggressively rate-limited (429); retry with backoff.
    """
    q = urllib.parse.quote(query)
    url = (f"https://api.semanticscholar.org/graph/v1/paper/search?query={q}"
           f"&limit={max_results}&fields=title,year,citationCount,abstract,url,externalIds")
    delay = 3.0
    for attempt in range(retries):
        try:
            data = json.loads(_get(url))
            out = []
            for p in data.get("data", []) or []:
                out.append({"source": "semantic_scholar",
                            "title": p.get("title", ""),
                            "url": p.get("url", ""),
                            "year": p.get("year"),
                            "citations": p.get("citationCount"),
                            "snippet": (p.get("abstract") or "")[:400]})
            return out
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            return []
        except Exception:
            return []
    return []


def tavily_search(query, max_results=6, api_key=None):
    """Web / product / patent-adjacent prior art via Tavily. Returns {title, url, snippet}.

    Requires TAVILY_API_KEY (env or arg). Returns [] if unset.
    """
    key = api_key or os.environ.get("TAVILY_API_KEY")
    if not key:
        return []
    body = {"api_key": key, "query": query, "max_results": max_results,
            "include_answer": False}
    req = urllib.request.Request(
        "https://api.tavily.com/search",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            data = json.loads(r.read().decode())
    except Exception:
        return []
    out = []
    for res in data.get("results", []) or []:
        out.append({"source": "web",
                    "title": res.get("title", ""),
                    "url": res.get("url", ""),
                    "snippet": (res.get("content") or "")[:400]})
    return out


def web_search_ddg(query, max_results=6):
    """Fallback: Tavily if a key is present, else empty (DDG html is captcha-walled)."""
    return tavily_search(query, max_results)


def research_mechanism(mechanism, max_per_source=4):
    """Run all sources for one mechanism phrase. Returns a dict of sourced hits."""
    results = {
        "mechanism": mechanism,
        "arxiv": arxiv_search(mechanism, max_per_source),
        "semantic_scholar": semantic_scholar_search(mechanism, max_per_source),
        "web": web_search_ddg(f"{mechanism} patent OR product OR existing", max_per_source),
    }
    time.sleep(1.0)  # be polite to the free APIs
    return results


def build_dossier(idea_title, mechanisms):
    """Research each mechanism and assemble a sourced novelty dossier.

    Returns a dict with per-mechanism sourced hits and a coarse prior-art density
    signal (more close hits -> more likely already disclosed).
    """
    dossier = {"idea": idea_title, "mechanisms": [], "prior_art_density": "unknown"}
    total_hits = 0
    for mech in mechanisms:
        r = research_mechanism(mech)
        hits = len(r["arxiv"]) + len(r["semantic_scholar"]) + len(r["web"])
        total_hits += hits
        dossier["mechanisms"].append(r)
    dossier["prior_art_density"] = (
        "high" if total_hits >= len(mechanisms) * 8 else
        "medium" if total_hits >= len(mechanisms) * 4 else
        "low"
    )
    return dossier


def dossier_to_text(dossier, max_mech=3, max_hits=3):
    """Render the dossier as compact sourced text for a backtest agent prompt."""
    lines = [f"RESEARCH DOSSIER for idea: {dossier['idea']}",
             f"prior-art density (coarse): {dossier['prior_art_density']}", ""]
    for mech in dossier["mechanisms"][:max_mech]:
        lines.append(f"Mechanism: {mech['mechanism']}")
        for src in ("arxiv", "semantic_scholar", "web"):
            for hit in mech[src][:max_hits]:
                t = hit.get("title", "")[:120]
                u = hit.get("url", "")
                lines.append(f"  - [{src}] {t} | {u}")
        lines.append("")
    return "\n".join(lines)
