#!/usr/bin/env python3
"""
Example: spawn a wave of Flashpoint agents in parallel, each with its own
mission, then tear them down. Demonstrates per-agent identity + traceability.

Usage:
  export FP_SPAWNER=http://<spawner-host>:2880
  python3 examples/spawn_wave.py --count 10 --tier ephemeral \
      --mission-prefix "Summarise document" [--destroy]
"""
import argparse, json, os, sys, time, urllib.request

SPAWNER = os.environ.get("FP_SPAWNER", "http://127.0.0.1:2880")

def call(method, path, body=None, timeout=30):
    req = urllib.request.Request(
        SPAWNER + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=10)
    ap.add_argument("--tier", default="ephemeral")
    ap.add_argument("--mission-prefix", default="task")
    ap.add_argument("--wave", default="1")
    ap.add_argument("--destroy", action="store_true")
    args = ap.parse_args()

    spawned = []
    t0 = time.perf_counter()
    for i in range(args.count):
        rec = call("POST", "/spawn", {
            "mission": f"{args.mission_prefix} #{i}",
            "tier": args.tier,
            "agent_id": f"wave-{args.wave}-agent-{i:05d}",   # deterministic, traceable
            "metadata": {"wave": args.wave, "index": i},
        })
        spawned.append(rec["agent_id"])
        print(f"spawned {rec['agent_id']} -> {rec.get('gateway_url')}")
    dt = time.perf_counter() - t0
    print(f"\nspawned {len(spawned)} agents in {dt:.2f}s "
          f"({len(spawned)/dt:.1f}/s)")

    print("\ncurrently running:")
    print(json.dumps(call("GET", "/agents"), indent=2))

    if args.destroy:
        t0 = time.perf_counter()
        for aid in spawned:
            call("DELETE", f"/agent/{aid}")
        dt = time.perf_counter() - t0
        print(f"destroyed {len(spawned)} agents in {dt:.2f}s")

if __name__ == "__main__":
    sys.exit(main())
