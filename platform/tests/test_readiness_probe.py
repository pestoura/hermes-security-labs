from __future__ import annotations

import importlib.util
import json
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "platform/assurance/readiness_probe.py"
spec = importlib.util.spec_from_file_location("readiness_probe", PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class Handler(BaseHTTPRequestHandler):
    payload = {
        "state": "ready",
        "observed_at": "2026-08-08T22:30:00Z",
        "ttl_seconds": 60,
    }

    def do_GET(self):
        body = json.dumps(self.payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


def _server(payload: dict):
    Handler.payload = payload
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_fresh_ready_probe_allows_fixed_effect() -> None:
    server, thread = _server({
        "state": "ready",
        "observed_at": "2026-08-08T22:30:00Z",
        "ttl_seconds": 60,
    })
    try:
        readiness = module.probe_http_readiness(
            url=f"http://127.0.0.1:{server.server_port}/ready",
            now=datetime(2026, 8, 8, 22, 30, 20, tzinfo=timezone.utc),
        )
        result = module.execute_after_readiness(readiness=readiness, effect=lambda: "EFFECT_EXECUTED")
        assert result == "EFFECT_EXECUTED"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_stale_readiness_blocks_effect_before_execution() -> None:
    server, thread = _server({
        "state": "ready",
        "observed_at": "2026-08-08T22:20:00Z",
        "ttl_seconds": 30,
    })
    called = False
    try:
        with pytest.raises(Exception, match="stale or invalid"):
            readiness = module.probe_http_readiness(
                url=f"http://127.0.0.1:{server.server_port}/ready",
                now=datetime(2026, 8, 8, 22, 30, 20, tzinfo=timezone.utc),
            )
            module.execute_after_readiness(readiness=readiness, effect=lambda: globals().update(called=True))
        assert called is False
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_non_local_readiness_endpoint_is_refused() -> None:
    with pytest.raises(module.ReadinessProbeError, match="CONTROLLED_LOCAL_READINESS_URL_REQUIRED"):
        module.probe_http_readiness(url="https://example.com/ready")
