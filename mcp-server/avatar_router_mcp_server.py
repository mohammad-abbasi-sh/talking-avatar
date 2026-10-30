#!/usr/bin/env python3
"""MCP server for talking-avatar — expose the router + preflight as tools.

Zero-dependency (Python standard library only). Speaks JSON-RPC 2.0
over stdio, newline-delimited, following the MCP lifecycle:

    initialize -> notifications/initialized -> tools/list -> tools/call

Tools:
    route_avatar_job
        job     job object (same schema as avatar_route.py --job, required)
    preflight_avatar
        image   portrait path (required)
        audio   audio path (optional)
        text    script text (optional, TTS route)
        language script language code, e.g. de (optional, default en)
    list_avatar_backends
        (no arguments)

The router/preflight run skills/talking-avatar/scripts/avatar_route.py
as a subprocess with --json; exit-code semantics are preserved in the
returned text (0 = route decided, 1 = preflight errors, 2 = usage error).
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROUTER = HERE.parent / "skills" / "talking-avatar" / "scripts" \
    / "avatar_route.py"

SERVER_INFO = {"name": "talking-avatar", "version": "0.1.0"}
PROTOCOL_VERSION = "2024-11-05"


def run_router(argv, job_payload=None):
    cmd = [sys.executable, str(ROUTER)] + argv + ["--json"]
    stdin_data = None
    if job_payload is not None:
        tmp = HERE / ".tmp-job.json"
        tmp.write_text(json.dumps(job_payload), encoding="utf-8")
        cmd += ["--job", str(tmp)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if job_payload is not None:
        try:
            tmp.unlink()
        except OSError:
            pass
    lines = [f"avatar_route exit code: {proc.returncode}"]
    try:
        payload = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    lines.append(json.dumps(payload, indent=2, ensure_ascii=False))
    if proc.stderr.strip():
        lines.append("stderr: " + proc.stderr.strip()[:500])
    return "\n".join(lines)


TOOLS = [
    {
        "name": "route_avatar_job",
        "description": (
            "Preflight a talking-avatar job's assets and route it to the "
            "right backend (sadtalker-local, sadtalker-cloud-gpu, hedra-api, "
            "heygen-api). Job fields: image, audio, text, language, "
            "duration_hint_s, budget (free|low|mid|any), quality "
            "(draft|good|studio), vram_gb, gpu_vendor "
            "(nvidia|amd|apple|none). Does not render or call APIs."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "job": {"type": "object",
                        "description": "job request object (see description)"},
            },
            "required": ["job"],
        },
    },
    {
        "name": "preflight_avatar",
        "description": (
            "Validate a talking-avatar portrait and audio/script without "
            "routing: catches corrupt files, tiny faces, wrong formats, "
            "over-long clips."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "image": {"type": "string"},
                "audio": {"type": "string"},
                "text": {"type": "string"},
                "language": {"type": "string"},
            },
            "required": ["image"],
        },
    },
    {
        "name": "list_avatar_backends",
        "description": "List the four routed backends with cost tiers and notes.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def handle_request(req):
    rid = req.get("id")
    method = req.get("method")
    params = req.get("params") or {}

    def ok(result):
        return {"jsonrpc": "2.0", "id": rid, "result": result}

    def err(code, message):
        return {"jsonrpc": "2.0", "id": rid,
                "error": {"code": code, "message": message}}

    if method == "initialize":
        return ok({"protocolVersion": PROTOCOL_VERSION,
                   "serverInfo": SERVER_INFO,
                   "capabilities": {"tools": {}}})
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return ok({"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            if name == "route_avatar_job":
                job = args.get("job")
                if not isinstance(job, dict):
                    raise ValueError("route_avatar_job requires 'job' object")
                text = run_router([], job_payload=job)
            elif name == "preflight_avatar":
                if not args.get("image"):
                    raise ValueError("preflight_avatar requires 'image'")
                job = {"image": args["image"], "audio": args.get("audio"),
                       "text": args.get("text"),
                       "language": args.get("language", "en"),
                       "budget": "any", "quality": "good",
                       "vram_gb": 0, "gpu_vendor": "none"}
                text = run_router([], job_payload=job)
            elif name == "list_avatar_backends":
                text = run_router(["--list-backends"])
            else:
                return err(-32602, f"unknown tool: {name}")
        except ValueError as e:
            return err(-32602, str(e))
        except subprocess.TimeoutExpired:
            return err(-32000, "router timed out")
        return ok({"content": [{"type": "text", "text": text}]})
    return err(-32601, f"unknown method: {method}")


def main():
    stdin = sys.stdin
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle_request(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
