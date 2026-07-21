#!/usr/bin/env python3
"""
Flashpoint — Agent Spawner API
Runs on a Docker host. Spawns and destroys ephemeral AI task agents.

  POST /spawn         create and start an agent
  GET  /agents        list running agents
  DELETE /agent/<id>  stop and remove an agent
  GET  /agent/<id>    lookup a single agent's spawn record (traceability)
  GET  /health        health check

Every spawn returns a unique agent_id plus a spawn record. The id is the
traceability anchor: it ties the live container, its gateway, its decision-log
rows, and (if the registry is enabled) a persistent spawn record to one identity.

Configuration is via environment variables (see .env.example). Never hardcode
credentials here.
"""

import http.server, json, subprocess, os, secrets, base64, threading, time, datetime
from urllib.parse import urlparse

# ---------------------------------------------------------------- config ---
PORT = int(os.environ.get("FP_SPAWNER_PORT", "2880"))
IMAGE = os.environ.get("FP_AGENT_IMAGE", "flashpoint/agent:latest")
# Decisions DB connection. Host + password come from the environment — never
# hardcode credentials here. Set FP_DECISIONS_HOST / FP_DECISIONS_PASS.
DECISIONS_HOST = os.environ.get("FP_DECISIONS_HOST", "")
DECISIONS_PASS = os.environ.get("FP_DECISIONS_PASS", "")
ORCHESTRATOR   = os.environ.get("FP_ORCHESTRATOR", "")
# Host address used when reporting per-agent gateway URLs. Defaults to this
# host's primary IP; override for multi-host / NAT / routed setups.
GATEWAY_HOST   = os.environ.get("FP_GATEWAY_HOST", "")
# Optional path for a JSONL spawn registry — one line per spawn, kept after
# teardown so an agent_id can always be traced back to its exact spawn.
REGISTRY_PATH  = os.environ.get("FP_REGISTRY_PATH", "")
# Default model for agents when the caller does not override it.
DEFAULT_MODEL  = os.environ.get("FP_DEFAULT_MODEL", "openrouter/anthropic/claude-opus-4-8")

TIER_RESOURCES = {
    "ephemeral": {"memory": "2048m", "cpus": "1.0"},
    "standard":  {"memory": "3072m", "cpus": "2.0"},
    "heavy":     {"memory": "6144m", "cpus": "4.0"},
}

_registry_lock = threading.Lock()

def docker(args):
    r = subprocess.run(["docker"] + args, capture_output=True, text=True)
    return r.stdout.strip(), r.stderr.strip(), r.returncode

def _gateway_host():
    if GATEWAY_HOST:
        return GATEWAY_HOST
    out, _, _ = docker(["info", "--format", "{{.DefaultAddressPools}}"])
    return "127.0.0.1"  # safe default; set FP_GATEWAY_HOST to advertise real host

def _registry_write(record):
    if not REGISTRY_PATH:
        return
    try:
        with _registry_lock, open(REGISTRY_PATH, "a") as f:
            f.write(json.dumps(record) + "\n")
    except OSError:
        pass  # registry is best-effort; never block a spawn on it

def _registry_read(agent_id):
    if not REGISTRY_PATH or not os.path.exists(REGISTRY_PATH):
        return None
    try:
        with open(REGISTRY_PATH) as f:
            for line in reversed(f.readlines()):
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("agent_id") == agent_id:
                    return rec
    except OSError:
        return None
    return None

def spawn_agent(mission, tier="ephemeral", soul_override=None, user_override=None,
                model=None, agent_id=None, openrouter_key=None, metadata=None):
    agent_id    = agent_id or f"fp-{secrets.token_hex(6)}"
    gw_token    = secrets.token_hex(32)
    resources   = TIER_RESOURCES.get(tier, TIER_RESOURCES["ephemeral"])

    env = [
        f"AS_AGENT_ID={agent_id}",
        f"AS_AGENT_TIER={tier}",
        f"AS_MISSION={mission}",
        f"AS_ORCHESTRATOR={ORCHESTRATOR}",
        f"AS_DECISIONS_HOST={DECISIONS_HOST}",
        f"AS_DECISIONS_PASS={DECISIONS_PASS}",
        f"OPENCLAW_TOKEN={gw_token}",
        f"AS_MODEL={model or DEFAULT_MODEL}",
    ]
    if openrouter_key:
        env.append(f"OPENROUTER_API_KEY={openrouter_key}")
    if soul_override:
        enc = base64.b64encode(soul_override.encode()).decode()
        env.append(f"SOUL_CONTENT={enc}")
    if user_override:
        enc = base64.b64encode(user_override.encode()).decode()
        env.append(f"USER_CONTENT={enc}")

    env_args = []
    for e in env:
        env_args += ["-e", e]

    cmd = [
        "run", "-d",
        "--name", agent_id,
        "--hostname", agent_id,
        "--memory", resources["memory"],
        "--cpus", resources["cpus"],
        "--restart", "no",
        "--network", "bridge",
        "-p", "0:18789",   # random host port → container 18789
        "--label", "fp.managed=true",
        "--label", f"fp.agent_id={agent_id}",
        "--label", f"fp.tier={tier}",
        "--label", f"fp.mission={mission[:80]}",
    ] + env_args + [IMAGE]

    stdout, stderr, code = docker(cmd)
    if code != 0:
        raise RuntimeError(f"Docker run failed: {stderr}")

    container_id = stdout[:12]

    # Get assigned host port
    port_out, _, _ = docker(["port", agent_id, "18789"])
    host_port = port_out.split(":")[-1] if port_out else None
    spawned_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    record = {
        "agent_id":     agent_id,
        "container_id": container_id,
        "tier":         tier,
        "mission":      mission,
        "gateway_url":  f"http://{_gateway_host()}:{host_port}" if host_port else None,
        "gateway_token": gw_token,
        "model":        model or DEFAULT_MODEL,
        "metadata":     metadata or {},
        "status":       "starting",
        "spawned_at":   spawned_at,
    }
    _registry_write({"event": "spawn", **record})
    return record

def list_agents():
    stdout, _, _ = docker([
        "ps", "--filter", "label=fp.managed=true",
        "--format", "{{.Names}}\t{{.Status}}\t{{.Ports}}\t{{.Label \"fp.tier\"}}\t{{.Label \"fp.mission\"}}"
    ])
    agents = []
    for line in stdout.splitlines():
        if line.strip():
            parts = line.split("\t")
            agents.append({
                "agent_id": parts[0] if len(parts) > 0 else "",
                "status":   parts[1] if len(parts) > 1 else "",
                "ports":    parts[2] if len(parts) > 2 else "",
                "tier":     parts[3] if len(parts) > 3 else "",
                "mission":  parts[4] if len(parts) > 4 else "",
            })
    return agents

def destroy_agent(agent_id):
    _, _, c1 = docker(["stop", agent_id])
    _, _, c2 = docker(["rm", agent_id])
    ok = c1 == 0 or c2 == 0
    if ok:
        _registry_write({"event": "destroy", "agent_id": agent_id,
                         "destroyed_at": datetime.datetime.now(datetime.timezone.utc).isoformat()})
    return ok

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress default logging

    def send_json(self, code, data):
        body = json.dumps(data, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        parts = path.strip("/").split("/")
        if path == "/health":
            self.send_json(200, {"status": "ok", "image": IMAGE})
        elif path == "/agents":
            agents = list_agents()
            self.send_json(200, {"agents": agents, "count": len(agents)})
        elif len(parts) == 2 and parts[0] == "agent":
            rec = _registry_read(parts[1])
            if rec:
                self.send_json(200, rec)
            else:
                # fall back to live container state if not in registry
                for a in list_agents():
                    if a["agent_id"] == parts[1]:
                        self.send_json(200, a)
                        return
                self.send_json(404, {"error": "agent not found"})
        else:
            self.send_json(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/spawn":
            length = int(self.headers.get("Content-Length", 0))
            body   = json.loads(self.rfile.read(length)) if length else {}
            try:
                result = spawn_agent(
                    mission       = body.get("mission", "no mission specified"),
                    tier          = body.get("tier", "ephemeral"),
                    soul_override = body.get("soul"),
                    user_override = body.get("user"),
                    model         = body.get("model"),
                    agent_id      = body.get("agent_id"),
                    openrouter_key= body.get("openrouter_key"),
                    metadata      = body.get("metadata"),
                )
                self.send_json(201, result)
            except Exception as e:
                self.send_json(500, {"error": str(e)})
        else:
            self.send_json(404, {"error": "not found"})

    def do_DELETE(self):
        path  = urlparse(self.path).path
        parts = path.strip("/").split("/")
        if len(parts) == 2 and parts[0] == "agent":
            ok = destroy_agent(parts[1])
            self.send_json(200 if ok else 404, {"destroyed": ok, "agent_id": parts[1]})
        else:
            self.send_json(404, {"error": "use DELETE /agent/<id>"})

if __name__ == "__main__":
    print(f"Flashpoint spawner starting on :{PORT}")
    print(f"Image: {IMAGE}")
    print(f"Decisions DB: {DECISIONS_HOST or '(disabled)'}")
    print(f"Registry: {REGISTRY_PATH or '(disabled)'}")
    server = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.serve_forever()
