from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import threading
from typing import Any
from urllib.parse import parse_qs, urlparse

LAB_ID = os.getenv("LAB_ID", "phase2-lab")
MODE = os.getenv("LAB_MODE", "source")
REPO = os.getenv("SOURCE_REPO", "")
COMMIT = os.getenv("SOURCE_COMMIT", "synthetic-v1")
MARKER = os.getenv("HERMES_PHASE2_SYNTHETIC_MARKER", f"{LAB_ID.upper().replace('-', '_')}_MARKER")
SOURCE = Path("/opt/hermes-lab/source").resolve()
MAX_BODY = 131072
RULES = [
    ("public-access", re.compile(r"(?i)(public[_ -]?read|0\.0\.0\.0/0|allUsers|anonymous)")),
    ("wildcard-action", re.compile(r"(?i)(actions?\s*[:=]\s*[\"']?\*|\"Action\"\s*:\s*\"\*\")")),
    ("unencrypted", re.compile(r"(?i)(encrypted\s*[:=]\s*false|storage_encrypted\s*=\s*false|http://)")),
    ("hardcoded-secret", re.compile(r"(?i)(password|secret|token|api[_-]?key)\s*[:=]\s*[\"'][^\"']{4,}[\"']")),
    ("unpinned-action", re.compile(r"uses:\s+[^@\s]+@(main|master|latest)\b")),
    ("curl-pipe-shell", re.compile(r"(?i)(curl|wget)[^\n|]*\|\s*(sh|bash)")),
]

def send(handler: BaseHTTPRequestHandler, status: int, payload: Any) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)

def body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    size = int(handler.headers.get("Content-Length", "0") or 0)
    if size < 0 or size > MAX_BODY:
        raise ValueError("invalid body size")
    value = json.loads(handler.rfile.read(size) if size else b"{}")
    if not isinstance(value, dict):
        raise ValueError("JSON object required")
    return value

def safe_path(relative: str) -> Path:
    candidate = (SOURCE / relative).resolve()
    if candidate != SOURCE and SOURCE not in candidate.parents:
        raise ValueError("path escapes source root")
    return candidate

def source_files(limit: int = 300) -> list[str]:
    result = []
    for path in sorted(SOURCE.rglob("*")):
        if path.is_file():
            result.append(str(path.relative_to(SOURCE)))
            if len(result) >= limit:
                break
    return result

def read_source(relative: str) -> str:
    path = safe_path(relative)
    if not path.is_file():
        raise FileNotFoundError(relative)
    return path.read_bytes()[:32768].decode(errors="replace")

def findings() -> list[dict[str, str]]:
    result = []
    for relative in source_files():
        path = safe_path(relative)
        if path.stat().st_size > 1048576:
            continue
        text = path.read_text(errors="ignore")
        for name, rule in RULES:
            if rule.search(text):
                result.append({"rule": name, "path": relative})
                if len(result) >= 200:
                    return result
    return result

def prompt_result(prompt: str) -> dict[str, Any]:
    detected = any(x in prompt.lower() for x in ("ignore previous", "system override", "reveal", "exfiltrate"))
    return {
        "injection_detected": detected,
        "vulnerable_response": f"synthetic-marker={MARKER}" if detected else "No override detected.",
        "real_secret_present": False,
    }

def rag_result(query: str) -> dict[str, Any]:
    poisoned = MODE == "rag" or any(x in query.lower() for x in ("admin", "secret"))
    documents = [{"id": "public", "poisoned": False}]
    if poisoned:
        documents.append({"id": "poisoned", "poisoned": True})
    return {"documents": documents, "vulnerable_answer": f"synthetic-marker={MARKER}" if poisoned else "public answer"}

def tools() -> list[dict[str, Any]]:
    result = [
        {"name": "read_source", "description": "Read an immutable source file.", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
        {"name": "analyze_source", "description": "Return deterministic source findings.", "inputSchema": {"type": "object", "properties": {}}},
    ]
    if MODE in {"mcp", "tool", "agent"}:
        result += [
            {"name": "execute_command", "description": "Training-only over-trusted tool; returns synthetic environment and never executes a command.", "inputSchema": {"type": "object", "properties": {"command": {"type": "string"}}}},
            {"name": "forward_env", "description": "Training-only forwarding semantic for caller-provided synthetic text.", "inputSchema": {"type": "object", "properties": {"value": {"type": "string"}}}},
        ]
    if MODE in {"rag", "llm"}:
        result.append({"name": "rag_query", "description": "Query a deterministic poisoned corpus.", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}})
    if MODE == "cicd":
        result.append({"name": "pipeline_status", "description": "Return synthetic CI state.", "inputSchema": {"type": "object", "properties": {}}})
    return result

def call_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "read_source":
        text = read_source(str(args.get("path", "README.md")))
    elif name == "analyze_source":
        text = json.dumps(findings())
    elif name == "execute_command" and MODE in {"mcp", "tool", "agent"}:
        text = json.dumps({"HERMES_PHASE2_SYNTHETIC_MARKER": MARKER, "COMMAND_EXECUTED": "no", "REAL_SECRET_PRESENT": "no"})
    elif name == "forward_env" and MODE in {"mcp", "tool", "agent"}:
        text = str(args.get("value", ""))[:1024]
    elif name == "rag_query" and MODE in {"rag", "llm"}:
        text = json.dumps(rag_result(str(args.get("query", ""))))
    elif name == "pipeline_status" and MODE == "cicd":
        text = json.dumps({"pipeline": "synthetic", "real_ci": False, "status": "vulnerable-training"})
    else:
        raise KeyError(name)
    return {"content": [{"type": "text", "text": text}]}

class App(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"app {fmt % args}", flush=True)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            send(self, 200, {"status": "ok", "lab": LAB_ID, "mode": MODE})
        elif parsed.path == "/api/meta":
            send(self, 200, {"lab": LAB_ID, "mode": MODE, "source_repo": REPO, "source_commit": COMMIT, "real_secrets": False})
        elif parsed.path == "/api/findings":
            send(self, 200, {"findings": findings()})
        elif parsed.path == "/api/source":
            relative = parse_qs(parsed.query).get("path", ["README.md"])[0]
            try:
                send(self, 200, {"path": relative, "content": read_source(relative)})
            except (ValueError, FileNotFoundError) as exc:
                send(self, 404, {"error": str(exc)})
        elif parsed.path == "/":
            send(self, 200, {"lab": LAB_ID, "mode": MODE})
        else:
            send(self, 404, {"error": "not found"})

    def do_POST(self) -> None:
        try:
            value = body(self)
            if self.path == "/api/chat":
                send(self, 200, prompt_result(str(value.get("prompt", ""))))
            elif self.path == "/api/query":
                send(self, 200, rag_result(str(value.get("query", ""))))
            elif self.path == "/api/pipeline":
                send(self, 200, {"pipeline": "synthetic", "real_ci": False})
            else:
                send(self, 404, {"error": "not found"})
        except (ValueError, json.JSONDecodeError) as exc:
            send(self, 400, {"error": str(exc)})

class MCP(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"mcp {fmt % args}", flush=True)

    def do_GET(self) -> None:
        send(self, 200 if self.path in {"/health", "/mcp/health"} else 405, {"status": "ok"})

    def do_POST(self) -> None:
        if self.path != "/mcp":
            send(self, 404, {"error": "not found"})
            return
        try:
            request = body(self)
            rpc_id, method = request.get("id"), request.get("method")
            params = request.get("params") or {}
            if method == "initialize":
                result = {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}}, "serverInfo": {"name": f"hermes-{LAB_ID}", "version": "1.0"}}
            elif method == "tools/list":
                result = {"tools": tools()}
            elif method == "tools/call":
                result = call_tool(str(params.get("name", "")), params.get("arguments") or {})
            else:
                send(self, 200, {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32601, "message": "Method not found"}})
                return
            send(self, 200, {"jsonrpc": "2.0", "id": rpc_id, "result": result})
        except KeyError as exc:
            send(self, 200, {"jsonrpc": "2.0", "id": None, "error": {"code": -32602, "message": f"Unknown tool: {exc.args[0]}"}})
        except (ValueError, json.JSONDecodeError) as exc:
            send(self, 400, {"error": str(exc)})

def serve(port: int, handler: type[BaseHTTPRequestHandler]) -> None:
    ThreadingHTTPServer(("0.0.0.0", port), handler).serve_forever()

if __name__ == "__main__":
    threading.Thread(target=serve, args=(8090, MCP), daemon=True).start()
    serve(8080, App)
