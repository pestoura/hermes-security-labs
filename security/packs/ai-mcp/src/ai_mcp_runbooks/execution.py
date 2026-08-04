"""Allowlisted local HTTP execution for the AI/MCP pack.

Two transports are provided, both refusing anything outside the laboratory
allowlist:

``LocalHttpTransport``
    Standard-library ``urllib`` client. No subprocess is created at all, so
    no shell can ever be involved and the prompt body never reaches an argv
    or a process listing.

``CurlCommandTransport``
    Optional fallback used where only ``curl`` is available. The argv is
    fixed and rendered by this module (never from payload text), it runs with
    ``shell=False`` and the request body is passed on stdin, never on argv.

Both transports enforce a connect/read timeout and a response byte budget.
"""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlsplit

#: Executables the pack may invoke. Everything else is refused.
ALLOWED_BINARIES = frozenset({"curl"})

#: Hostnames reachable from the attacker container / host under test.
ALLOWED_HOSTS = frozenset(
    {
        "target",
        "localhost",
        "127.0.0.1",
        "promptme",
        "promptme-target",
    }
)

#: Only plain HTTP inside the isolated laboratory network.
ALLOWED_SCHEMES = frozenset({"http"})

#: Ports published by the Phase 2 safe-lab runtime and its host proxy.
ALLOWED_PORTS = frozenset({8080, 8090, 8210, 8211, 8212, 8213, 8214, 8215, 8216})

DEFAULT_TIMEOUT_SECONDS = 10
MAX_RESPONSE_BYTES = 262144
MAX_REQUEST_BYTES = 8192
#: Maximum number of HTTP interactions a single handler run may perform.
MAX_REQUEST_BUDGET = 12


class CommandError(RuntimeError):
    """Raised when a request cannot be executed under the policy."""


@dataclass(frozen=True)
class HttpResponse:
    """Raw (unsanitised) HTTP response, never returned to the caller as-is."""

    url: str
    status: int | None
    body: str
    error: str | None = None
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.status is not None and not self.timed_out and self.error is None

    def json(self) -> Any:
        try:
            return json.loads(self.body)
        except (ValueError, TypeError):
            return None


class HttpTransport(Protocol):
    def request(
        self,
        url: str,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> HttpResponse: ...


def validate_base_url(base_url: str) -> str:
    """Validate ``base_url`` against the transport allowlist.

    The payload may only select among already-allowed hosts/ports; it can
    never widen the allowlist.
    """

    if not isinstance(base_url, str) or not base_url.strip():
        raise CommandError("base_url must be a non-empty string")
    parts = urlsplit(base_url.strip())
    if parts.scheme not in ALLOWED_SCHEMES:
        raise CommandError(f"scheme {parts.scheme!r} is not allowlisted")
    if parts.hostname is None or parts.hostname not in ALLOWED_HOSTS:
        raise CommandError(f"host {parts.hostname!r} is not allowlisted")
    port = parts.port or 80
    if port not in ALLOWED_PORTS:
        raise CommandError(f"port {port} is not allowlisted")
    if parts.query or parts.fragment:
        raise CommandError("base_url must not carry a query or fragment")
    return f"{parts.scheme}://{parts.netloc}"


def build_url(base_url: str, path: str) -> str:
    """Join a validated base URL with a fixed, module-defined path."""

    if not path.startswith("/"):
        raise CommandError("path must start with '/'")
    return validate_base_url(base_url).rstrip("/") + path


@dataclass
class LocalHttpTransport:
    """Standard-library HTTP transport; creates no subprocess."""

    timeout: int = DEFAULT_TIMEOUT_SECONDS
    max_bytes: int = MAX_RESPONSE_BYTES

    def request(
        self,
        url: str,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        timeout: int | None = None,
    ) -> HttpResponse:
        if method not in {"GET", "POST"}:
            raise CommandError(f"method {method!r} is not allowlisted")
        validate_base_url(url)
        data: bytes | None = None
        headers = {"Accept": "application/json", "User-Agent": "hermes-ai-mcp-probe/1"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            if len(data) > MAX_REQUEST_BYTES:
                raise CommandError("request body exceeds the size budget")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        effective = int(timeout or self.timeout)
        try:
            with urllib.request.urlopen(request, timeout=effective) as response:  # noqa: S310
                body = response.read(self.max_bytes).decode("utf-8", errors="replace")
                return HttpResponse(url=url, status=int(response.status), body=body)
        except urllib.error.HTTPError as exc:
            body = exc.read(self.max_bytes).decode("utf-8", errors="replace") if exc.fp else ""
            return HttpResponse(url=url, status=int(exc.code), body=body)
        except TimeoutError:
            return HttpResponse(url=url, status=None, body="", error="timeout", timed_out=True)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return HttpResponse(url=url, status=None, body="", error=type(exc).__name__)


@dataclass
class CurlCommandTransport:
    """Fixed-argv ``curl`` transport, ``shell=False``, body passed on stdin."""

    timeout: int = DEFAULT_TIMEOUT_SECONDS
    max_bytes: int = MAX_RESPONSE_BYTES

    def build_argv(self, url: str, method: str, has_body: bool) -> list[str]:
        validate_base_url(url)
        if method not in {"GET", "POST"}:
            raise CommandError(f"method {method!r} is not allowlisted")
        argv = [
            "curl",
            "--silent",
            "--show-error",
            "--request",
            method,
            "--max-time",
            str(int(self.timeout)),
            "--max-filesize",
            str(int(self.max_bytes)),
            "--write-out",
            "\\n__HTTP_STATUS__:%{http_code}",
        ]
        if has_body:
            argv += ["--header", "Content-Type: application/json", "--data-binary", "@-"]
        argv.append(url)
        if argv[0] not in ALLOWED_BINARIES:
            raise CommandError(f"binary {argv[0]!r} is not allowlisted")
        return argv

    def request(
        self,
        url: str,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        timeout: int | None = None,
    ) -> HttpResponse:
        body_bytes = json.dumps(payload).encode("utf-8") if payload is not None else None
        if body_bytes is not None and len(body_bytes) > MAX_REQUEST_BYTES:
            raise CommandError("request body exceeds the size budget")
        argv = self.build_argv(url, method, body_bytes is not None)
        try:
            completed = subprocess.run(  # noqa: S603 - fixed argv, shell=False
                argv,
                input=body_bytes,
                capture_output=True,
                timeout=int(timeout or self.timeout),
                check=False,
                shell=False,
            )
        except FileNotFoundError as exc:
            raise CommandError("binary 'curl' is not available on this host") from exc
        except subprocess.TimeoutExpired:
            return HttpResponse(url=url, status=None, body="", error="timeout", timed_out=True)
        stdout = (completed.stdout or b"")[: self.max_bytes].decode("utf-8", errors="replace")
        status, body = parse_http_status(stdout)
        if status is None:
            return HttpResponse(url=url, status=None, body=body, error="unreachable")
        return HttpResponse(url=url, status=status, body=body)


def parse_http_status(stdout: str) -> tuple[int | None, str]:
    """Split the curl write-out marker from the body."""

    marker = "__HTTP_STATUS__:"
    index = stdout.rfind(marker)
    if index == -1:
        return None, stdout
    body = stdout[:index].rstrip("\n")
    raw = stdout[index + len(marker):].strip()
    try:
        status = int(raw)
    except ValueError:
        return None, body
    return (status if status > 0 else None), body


@dataclass
class RequestBudget:
    """Hard cap on the number of HTTP interactions per handler run."""

    limit: int = MAX_REQUEST_BUDGET
    used: int = field(default=0)

    def consume(self) -> None:
        if self.used >= self.limit:
            raise CommandError(f"request budget of {self.limit} interactions exhausted")
        self.used += 1


def describe(response: HttpResponse) -> dict[str, Any]:
    """Non-sensitive description of an HTTP interaction."""

    return {
        "http_status": response.status,
        "timed_out": response.timed_out,
        "body_bytes": len(response.body.encode("utf-8", errors="replace")),
        "transport_error": response.error,
    }
