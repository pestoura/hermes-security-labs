#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

ALLOWED_HANDLERS = {
    "fuzz",
    "graphql",
    "headers",
    "http",
    "jwt",
    "nuclei",
    "openapi",
    "race",
    "sqlmap",
    "tls",
    "websocket",
    "workflow",
}


def fail(message: str, code: int = 2) -> None:
    print(json.dumps({"status": "error", "error": message}))
    raise SystemExit(code)


def allowed_host(url: str) -> str:
    host = urllib.parse.urlparse(url).hostname
    if not host:
        fail("URL has no hostname")
    allowed = {
        value.strip()
        for value in os.environ.get("HEX0R_ALLOWED_HOSTS", "").split(",")
        if value.strip()
    }
    if host not in allowed:
        fail(f"host {host!r} is not allowlisted")
    return host


def run_argv(argv: list[str], timeout: int) -> dict[str, Any]:
    completed = subprocess.run(
        argv,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return {
        "status": "completed" if completed.returncode == 0 else "failed",
        "exit_code": completed.returncode,
        "stdout": completed.stdout[-65536:],
        "stderr": completed.stderr[-16384:],
    }


def http_action(request: dict[str, Any]) -> dict[str, Any]:
    args = request["arguments"]
    url = args["url"]
    allowed_host(url)
    method = args.get("method", "GET").upper()
    headers = {str(key): str(value) for key, value in args.get("headers", {}).items()}
    body = args.get("body")
    if isinstance(body, (dict, list)):
        data = json.dumps(body).encode()
    elif body is not None:
        data = str(body).encode()
    else:
        data = None
    request_object = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(
            request_object,
            timeout=request["limits"]["timeout_seconds"],
        ) as response:
            content = response.read(request["limits"]["max_response_bytes"])
            return {
                "status": "completed",
                "status_code": response.status,
                "headers": dict(response.headers),
                "body_sample": content.decode(errors="replace"),
            }
    except urllib.error.HTTPError as exc:
        content = exc.read(request["limits"]["max_response_bytes"])
        return {
            "status": "completed",
            "status_code": exc.code,
            "headers": dict(exc.headers),
            "body_sample": content.decode(errors="replace"),
        }


def external_action(request: dict[str, Any]) -> dict[str, Any]:
    args = request["arguments"]
    url = args.get("url") or args.get("target")
    if url:
        allowed_host(url)
    handler = request["handler"]
    profile = request["profile"]
    timeout = request["limits"]["timeout_seconds"]
    if handler == "tls":
        host = allowed_host(args["url"])
        port = str(args.get("port", 443))
        return run_argv(
            ["nmap", "-Pn", "-p", port, "--script", "ssl-enum-ciphers,ssl-cert", host],
            timeout,
        )
    if handler == "nuclei":
        return run_argv(
            ["nuclei", "-u", url, "-jsonl", "-silent", "-tags", profile],
            timeout,
        )
    if handler == "sqlmap":
        return run_argv(
            [
                "sqlmap",
                "-u",
                url,
                "--batch",
                "--level=1",
                "--risk=1",
                "--output-dir=/tmp/sqlmap-output",
            ],
            timeout,
        )
    if handler == "fuzz":
        wordlist = args.get(
            "wordlist",
            "/usr/share/seclists/Discovery/Web-Content/api/api-endpoints.txt",
        )
        return run_argv(
            ["ffuf", "-u", url, "-w", wordlist, "-of", "json", "-s"],
            timeout,
        )
    if handler == "jwt":
        token_ref = args.get("token_file", "/run/secrets/token")
        return run_argv(
            [
                "python3",
                "/opt/jwt_tool/jwt_tool.py",
                "-t",
                url,
                "-rh",
                f"Authorization: Bearer @{token_ref}",
                "-M",
                "at",
            ],
            timeout,
        )
    if handler == "websocket":
        return run_argv(["websocat", "-n1", url], timeout)
    if handler in {"openapi", "graphql", "headers", "workflow", "race"}:
        return http_action(request)
    fail(f"handler/profile not implemented: {handler}/{profile}")
    return {}


def execute(request: dict[str, Any]) -> dict[str, Any]:
    handler = request.get("handler")
    if handler not in ALLOWED_HANDLERS:
        fail(f"handler {handler!r} is not allowed")
    if handler == "http":
        return http_action(request)
    return external_action(request)


def main() -> None:
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command", required=True)
    execute_parser = subcommands.add_parser("execute")
    execute_parser.add_argument("--payload-b64", required=True)
    args = parser.parse_args()
    try:
        decoded = base64.urlsafe_b64decode(args.payload_b64.encode())
        request = json.loads(decoded)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        fail(f"invalid payload: {exc}")
    print(json.dumps(execute(request)))


if __name__ == "__main__":
    main()
