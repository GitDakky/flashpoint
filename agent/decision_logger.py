#!/usr/bin/env python3
"""
Agent Decision Logger — write decisions to as-pgvector from inside an agent container.
Usage: python3 /root/clawd/decision_logger.py "<decision>" "<reasoning>" [--outcome success|failure|pending] [--confidence 0.9] [--tags tag1,tag2]
"""
import os, sys, json, argparse, psycopg2
from datetime import datetime, timezone

def log_decision(decision, reasoning, outcome="pending", confidence=None, tags=None, alternatives=None):
    host     = os.environ.get("AS_DECISIONS_HOST", "")
    password = os.environ.get("AS_DECISIONS_PASS", "")
    agent_id = os.environ.get("AS_AGENT_ID", f"docker-{os.getpid()}")
    tier     = os.environ.get("AS_AGENT_TIER", "ephemeral")
    mission  = os.environ.get("AS_MISSION", "")

    if not password:
        print("AS_DECISIONS_PASS not set — skipping decision log", file=sys.stderr)
        return None

    conn = psycopg2.connect(
        host=host, port=5432, dbname="decisions",
        user="agent_writer", password=password,
        options="-c client_encoding=UTF8", connect_timeout=10
    )
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO agent_decisions
          (agent_id, agent_type, mission, decision, reasoning, alternatives,
           confidence, outcome, tags, timestamp)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id
    """, (
        agent_id, tier, mission, decision, reasoning,
        alternatives, confidence, outcome,
        tags or [], datetime.now(timezone.utc)
    ))
    row_id = cur.fetchone()[0]
    conn.commit()
    conn.close()
    print(f"Decision logged: {row_id}")
    return str(row_id)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("decision")
    ap.add_argument("reasoning")
    ap.add_argument("--outcome",      default="pending")
    ap.add_argument("--confidence",   type=float, default=None)
    ap.add_argument("--tags",         default="")
    ap.add_argument("--alternatives", default=None)
    args = ap.parse_args()
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    log_decision(args.decision, args.reasoning, args.outcome, args.confidence, tags, args.alternatives)
