#!/usr/bin/env python3
"""
flashpoint-intake — push mission data into Flashpoint en masse.

Data sources (missions + variants already created):
  --manifest <file>     JSON list or JSONL of spawn objects
  --csv <file>          CSV with a `mission` column (+ optional tier/model/agent_id)
  --from-db <dsn>       Postgres DSN; requires --query returning one mission column

Variant generation (an agent produces the variants for you):
  --generate '<base mission>' --variants N [--variant-model <model>]
                        Uses one agent to expand a base mission into N variants,
                        then spawns them all.

Targeting a fleet: --spawners accepts several spawner URLs and missions are
sharded across them round-robin (each batch goes to one spawner's /spawn_batch).

Examples:
  python3 intake/flashpoint_intake.py --spawners http://10.0.0.5:2880 \
      --manifest missions.json --batch wave-1
  python3 intake/flashpoint_intake.py --spawners http://s1:2880,http://s2:2880 \
      --generate 'analyse a quarterly financial report' --variants 25 --batch q1
"""
import argparse, csv, json, os, secrets, sys, time, urllib.request

def call(base, method, path, body=None, timeout=300):
    req = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

# ---------- data sources ----------
def from_manifest(path):
    spawns = []
    with open(path) as f:
        text = f.read().strip()
    if text.startswith("["):
        rows = json.loads(text)
    else:  # JSONL
        rows = [json.loads(l) for l in text.splitlines() if l.strip()]
    for row in rows:
        spawns.append(row if "mission" in row else {"mission": str(row)})
    return spawns

def from_csv(path):
    spawns = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            item = {"mission": row.get("mission", "")}
            for k in ("tier", "model", "agent_id", "soul", "user"):
                if row.get(k):
                    item[k] = row[k]
            spawns.append(item)
    return spawns

def from_db(dsn, query):
    import psycopg2  # optional dep, only needed for --from-db
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute(query)
    spawns = [{"mission": r[0]} for r in cur.fetchall()]
    conn.close()
    return spawns

# ---------- variant generation ----------
def generate_variants(spawner, base_mission, n, model=None, key=None):
    """Spawn one agent to author N mission variants, return them as spawn objects."""
    gen_mission = (
        f"Generate {n} distinct task-agent mission variants based on this base mission:\n"
        f"\"{base_mission}\"\n\n"
        f"Return ONLY a JSON array of {n} mission strings, each self-contained and "
        f"actionable by an autonomous agent. No prose, no numbering, no markdown — "
        f"just the JSON array of strings."
    )
    rec = call(spawner, "POST", "/spawn", {
        "mission": gen_mission, "tier": "standard",
        "model": model, "openrouter_key": key,
        "agent_id": f"fp-variantgen-{secrets.token_hex(3)}",
        "metadata": {"role": "variant-generator"},
    })
    gw = rec.get("gateway_url")
    tok = rec.get("gateway_token")
    gid = rec.get("agent_id")
    variants = []
    try:
        if gw and tok:
            # Ask the generator agent's gateway for its answer.
            for _ in range(60):  # up to ~5 min
                time.sleep(5)
                try:
                    out = call(gw, "POST", "/api/chat", {"message": "return the JSON array now"}, timeout=30)
                except Exception:
                    continue
                text = json.dumps(out)
                start = text.find("[")
                if start != -1:
                    try:
                        arr = json.loads(text[start:text.rfind("]") + 1])
                        variants = [str(v) for v in arr if str(v).strip()]
                        if variants:
                            break
                    except Exception:
                        continue
    finally:
        try:
            call(spawner, "DELETE", f"/agent/{gid}")
        except Exception:
            pass
    if not variants:  # fallback: mechanical suffix variants if generation fails
        variants = [f"{base_mission} (variant {i+1})" for i in range(n)]
    return [{"mission": v, "metadata": {"generated": True}} for v in variants[:n]]

# ---------- shard + push ----------
def shard(items, n):
    n = max(1, n)
    buckets = [[] for _ in range(n)]
    for i, item in enumerate(items):
        buckets[i % n].append(item)
    return [b for b in buckets if b]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spawners", required=True, help="comma-separated spawner base URLs")
    ap.add_argument("--batch", default=None, help="batch id (default: generated)")
    ap.add_argument("--tier", default="ephemeral")
    ap.add_argument("--model", default=None)
    ap.add_argument("--openrouter-key", default=os.environ.get("OPENROUTER_API_KEY"))
    ap.add_argument("--max-parallel", type=int, default=8)
    ap.add_argument("--manifest"); ap.add_argument("--csv"); ap.add_argument("--from-db"); ap.add_argument("--query")
    ap.add_argument("--generate"); ap.add_argument("--variants", type=int, default=10); ap.add_argument("--variant-model")
    args = ap.parse_args()

    spawners = [s.strip().rstrip("/") for s in args.spawners.split(",") if s.strip()]
    batch = args.batch or f"batch-{secrets.token_hex(3)}"

    if args.manifest:
        spawns = from_manifest(args.manifest)
    elif args.csv:
        spawns = from_csv(args.csv)
    elif args.from_db and args.query:
        spawns = from_db(args.from_db, args.query)
    elif args.generate:
        print(f"generating {args.variants} variants via an agent on {spawners[0]} ...")
        spawns = generate_variants(spawners[0], args.generate, args.variants, args.variant_model, args.openrouter_key)
    else:
        ap.error("provide a data source: --manifest, --csv, --from-db, or --generate")

    if not spawns:
        print("no missions to spawn"); return 1

    print(f"batch={batch}  total_missions={len(spawns)}  spawners={len(spawners)}")
    buckets = shard(spawns, len(spawners))
    total_ok = total_fail = 0
    t0 = time.perf_counter()
    for spawner, bucket in zip(spawners, buckets):
        print(f"-> {spawner}: spawning {len(bucket)}")
        try:
            res = call(spawner, "POST", "/spawn_batch", {
                "batch_id": batch, "spawns": bucket, "tier": args.tier,
                "model": args.model, "openrouter_key": args.openrouter_key,
                "max_parallel": args.max_parallel,
            })
            ok = sum(1 for r in res.get("results", []) if r.get("ok"))
            fail = len(res.get("results", [])) - ok
            total_ok += ok; total_fail += fail
            print(f"   ok={ok} failed={fail}")
        except Exception as e:
            print(f"   ERROR contacting {spawner}: {e}")
            total_fail += len(bucket)
    dt = time.perf_counter() - t0
    print(f"\nDONE batch={batch} spawned={total_ok} failed={total_fail} in {dt:.1f}s "
          f"({(total_ok/dt) if dt else 0:.1f}/s)")
    return 0 if total_fail == 0 else 2

if __name__ == "__main__":
    sys.exit(main())
