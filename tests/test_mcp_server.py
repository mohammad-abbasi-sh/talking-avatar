#!/usr/bin/env python3
"""End-to-end tests for the talking-avatar MCP server (stdio JSON-RPC)."""
import json
import struct
import subprocess
import sys
import wave
import zlib
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SERVER = HERE.parent / "mcp-server" / "avatar_router_mcp_server.py"


def make_png(path, w=512, h=512):
    ihdr_data = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data
    ihdr += struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF)
    row = b"\x00" + b"\x80" * (w * 3)
    idat_data = zlib.compress(row * h)
    idat = struct.pack(">I", len(idat_data)) + b"IDAT" + idat_data
    idat += struct.pack(">I", zlib.crc32(b"IDAT" + idat_data) & 0xFFFFFFFF)
    iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + ihdr + idat + iend)


def make_wav(path, seconds=5):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(seconds * 16000))


class McpClient:
    """Minimal stdio JSON-RPC client for the server under test."""

    def __init__(self):
        self.proc = subprocess.Popen(
            [sys.executable, str(SERVER)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1)
        self._id = 0

    def call(self, method, params=None, expect_response=True):
        self._id += 1
        req = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            req["params"] = params
        self.proc.stdin.write(json.dumps(req) + "\n")
        self.proc.stdin.flush()
        if not expect_response:
            return None
        line = self.proc.stdout.readline()
        assert line, "server closed stdout"
        return json.loads(line)

    def close(self):
        try:
            self.proc.stdin.close()
        except BrokenPipeError:
            pass
        self.proc.terminate()
        self.proc.wait(timeout=10)


@pytest.fixture()
def client():
    c = McpClient()
    yield c
    c.close()


@pytest.fixture()
def assets(tmp_path):
    make_png(tmp_path / "face.png")
    make_wav(tmp_path / "voice.wav")
    return tmp_path


def init(client):
    r = client.call("initialize", {"protocolVersion": "2024-11-05"})
    assert r["result"]["serverInfo"]["name"] == "talking-avatar"
    client.call("notifications/initialized", expect_response=False)


def tool_names(client):
    r = client.call("tools/list")
    return [t["name"] for t in r["result"]["tools"]]


def call_tool(client, name, arguments):
    r = client.call("tools/call",
                    {"name": name, "arguments": arguments})
    assert "error" not in r, r
    return r["result"]["content"][0]["text"]


class TestLifecycle:
    def test_initialize(self, client):
        init(client)

    def test_tools_list(self, client):
        init(client)
        names = tool_names(client)
        assert names == ["route_avatar_job", "preflight_avatar",
                         "list_avatar_backends"]

    def test_unknown_method_errors(self, client):
        r = client.call("nope/method")
        assert "error" in r

    def test_unknown_tool_errors(self, client):
        init(client)
        r = client.call("tools/call",
                        {"name": "nope", "arguments": {}})
        assert "error" in r


class TestTools:
    def test_list_backends(self, client):
        init(client)
        text = call_tool(client, "list_avatar_backends", {})
        assert "sadtalker-local" in text and "heygen-api" in text

    def test_route_avatar_job(self, client, assets):
        init(client)
        job = {"image": str(assets / "face.png"),
               "audio": str(assets / "voice.wav"),
               "language": "de", "budget": "free", "quality": "good",
               "vram_gb": 8, "gpu_vendor": "nvidia"}
        text = call_tool(client, "route_avatar_job", {"job": job})
        assert "avatar_route exit code: 0" in text
        assert "sadtalker-local" in text

    def test_route_requires_job_object(self, client):
        init(client)
        r = client.call("tools/call",
                        {"name": "route_avatar_job",
                         "arguments": {"job": "not-an-object"}})
        assert "error" in r

    def test_preflight_ok(self, client, assets):
        init(client)
        text = call_tool(client, "preflight_avatar",
                         {"image": str(assets / "face.png"),
                          "audio": str(assets / "voice.wav")})
        assert "avatar_route exit code: 0" in text

    def test_preflight_missing_image(self, client, assets):
        init(client)
        text = call_tool(client, "preflight_avatar",
                         {"image": str(assets / "gone.png"),
                          "audio": str(assets / "voice.wav")})
        assert "avatar_route exit code: 1" in text
        assert "IMAGE-01" in text

    def test_preflight_requires_image(self, client):
        init(client)
        r = client.call("tools/call",
                        {"name": "preflight_avatar", "arguments": {}})
        assert "error" in r
