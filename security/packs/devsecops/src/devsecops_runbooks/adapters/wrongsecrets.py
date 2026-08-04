"""Calibrated adapter for the OWASP WrongSecrets laboratory.

Scope of the calibration
------------------------

WrongSecrets is a *secrets management* laboratory: its challenges expose
hard-coded credentials through the application itself. The calibrated control
implemented here answers one measurable question:

    does the running laboratory expose secret material through unauthenticated
    HTTP surfaces?

The adapter performs read-only HTTP GETs against the laboratory proxy on the
isolated network, classifies the responses and returns a functional decision.
It never returns, logs or stores the challenge values it detects: detection is
reported as rule identifiers and counts only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from devsecops_runbooks.contracts import (
    Decision,
    Evidence,
    ExecutionRequest,
    ExecutionResult,
    Status,
)
from devsecops_runbooks.execution import (
    CommandError,
    CommandResult,
    CommandRunner,
    LocalCommandRunner,
    build_http_probe,
    describe,
    parse_http_status,
)
from devsecops_runbooks.sanitizer import sanitize_text

LABORATORY_ID = "wrongsecrets"
DEFAULT_BASE_URL = "http://wrongsecrets:8080"

#: Upper bound for a single probe body. The WrongSecrets landing page is
#: ~85 KiB, so a smaller cap makes curl abort with exit 63 and the surface
#: would be misreported as unreachable.
PROBE_MAX_BYTES = 262144

#: Read-only surfaces probed by the control, in order.
PROBE_PATHS: tuple[tuple[str, str], ...] = (
    ("liveness", "/actuator/health"),
    ("application-root", "/"),
    ("challenge-detail", "/challenge/challenge-1"),
    ("challenge-spoiler", "/spoil/challenge-1"),
    ("configuration-surface", "/actuator/env"),
)

#: Detection rules. Only the rule id is ever reported, never the match.
DETECTION_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("hardcoded-secret-marker", re.compile(r"(?i)wrongsecrets_synthetic_marker")),
    ("aws-access-key-id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}\b")),
    ("private-key-block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    (
        "credential-assignment",
        re.compile(r"(?i)\b(password|passphrase|secret|api[_-]?key)\b\s*[:=]\s*[^\s\"'<>]{6,}"),
    ),
)

#: Actuator endpoints that must not be reachable unauthenticated.
SENSITIVE_SURFACES = {"configuration-surface"}

#: Surfaces whose purpose is to disclose a challenge answer. Reaching one of
#: them unauthenticated is an exposure signal by itself; the disclosed value is
#: never read, stored or reported.
SPOILER_SURFACES = {"challenge-spoiler"}

#: Structural marker of a rendered spoiler block carrying a non-empty answer.
SPOILER_DISCLOSURE = re.compile(r"(?is)<[^>]*spoiler[^>]*>(?:\s|<[^>]+>)*[^<\s]{6,}")


@dataclass
class ProbeOutcome:
    """Classified outcome of a single probe, without secret material."""

    name: str
    path: str
    reachable: bool
    http_status: int | None
    matched_rules: tuple[str, ...]
    body_bytes: int
    disclosure: bool = False
    command: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_evidence(self) -> Evidence:
        return Evidence(
            ref=f"probe/{self.name}",
            kind="http-probe",
            value={
                "path": self.path,
                "reachable": self.reachable,
                "http_status": self.http_status,
                "matched_rules": list(self.matched_rules),
                "body_bytes": self.body_bytes,
                "disclosure": self.disclosure,
                "error": self.error,
                "command": self.command,
            },
        )


def detect_rules(body: str) -> tuple[str, ...]:
    """Return the identifiers of detection rules that matched ``body``.

    The matched text is intentionally discarded.
    """

    return tuple(rule_id for rule_id, pattern in DETECTION_RULES if pattern.search(body))


@dataclass
class WrongSecretsAdapter:
    """Real, calibrated adapter for the ``secrets/scan`` handler."""

    runner: CommandRunner = field(default_factory=LocalCommandRunner)
    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: int = 20

    def probe(self, name: str, path: str) -> ProbeOutcome:
        try:
            argv = build_http_probe(
                self.base_url, path, timeout=self.timeout_seconds, max_bytes=PROBE_MAX_BYTES
            )
        except CommandError as exc:
            return ProbeOutcome(name, path, False, None, (), 0, error=str(exc))
        try:
            result: CommandResult = self.runner.run(argv, timeout=self.timeout_seconds)
        except CommandError as exc:
            return ProbeOutcome(name, path, False, None, (), 0, error=str(exc))

        status, body = parse_http_status(result.stdout)
        reachable = status is not None and result.exit_code == 0 and not result.timed_out
        disclosure = bool(
            reachable
            and name in SPOILER_SURFACES
            and status == 200
            and SPOILER_DISCLOSURE.search(body)
        )
        return ProbeOutcome(
            name=name,
            path=path,
            reachable=reachable,
            http_status=status,
            matched_rules=detect_rules(body) if reachable else (),
            body_bytes=len(body.encode("utf-8", errors="replace")),
            disclosure=disclosure,
            command=describe(result),
            error=None if reachable else sanitize_text(result.stderr or "unreachable", 256) or "unreachable",
        )

    def run(self, request: ExecutionRequest) -> ExecutionResult:
        base_url = request.arguments.get("base_url") or self.base_url
        if not isinstance(base_url, str):
            return ExecutionResult.error("argument 'base_url' must be a string", request)
        self.base_url = base_url

        outcomes = [self.probe(name, path) for name, path in PROBE_PATHS]
        reachable = [item for item in outcomes if item.reachable]

        vulnerable_signals: list[str] = []
        secure_signals: list[str] = []
        inconclusive_signals: list[str] = []

        if not reachable:
            inconclusive_signals.append("target.unreachable")
            return ExecutionResult(
                status=Status.OK,
                decision=Decision.INCONCLUSIVE,
                provider=request.provider,
                action=request.action,
                profile=request.profile,
                target_ref=request.target_ref,
                scope=request.scope,
                control_id=request.control_id,
                reason="no laboratory surface responded; start the laboratory before scanning",
                inconclusive_signals=tuple(inconclusive_signals),
                evidence=tuple(item.to_evidence() for item in outcomes),
                meta={
                    "laboratory": LABORATORY_ID,
                    "base_url": base_url,
                    "probes_total": len(outcomes),
                    "probes_reachable": 0,
                },
            )

        matched_total = 0
        for item in reachable:
            if item.matched_rules:
                matched_total += len(item.matched_rules)
                vulnerable_signals.append(f"secret.exposed:{item.name}")
            if item.disclosure:
                vulnerable_signals.append(f"secret.answer_disclosed:{item.name}")
            elif item.name in SPOILER_SURFACES and item.http_status in (401, 403, 404):
                secure_signals.append(f"spoiler.protected:{item.name}")
            if item.name in SENSITIVE_SURFACES and item.http_status == 200:
                vulnerable_signals.append(f"actuator.exposed:{item.name}")
            elif item.name in SENSITIVE_SURFACES and item.http_status in (401, 403, 404):
                secure_signals.append(f"actuator.protected:{item.name}")

        if not vulnerable_signals:
            secure_signals.append("secret.no_exposure_detected")
            if len(reachable) < len(outcomes):
                inconclusive_signals.append("coverage.partial")

        decision = Decision.VULNERABLE if vulnerable_signals else Decision.SECURE
        reason = (
            f"{len(vulnerable_signals)} exposure signal(s) across {len(reachable)}"
            f"/{len(outcomes)} reachable surfaces"
            if vulnerable_signals
            else f"no exposure detected across {len(reachable)}/{len(outcomes)} reachable surfaces"
        )

        return ExecutionResult(
            status=Status.OK,
            decision=decision,
            provider=request.provider,
            action=request.action,
            profile=request.profile,
            target_ref=request.target_ref,
            scope=request.scope,
            control_id=request.control_id,
            reason=reason,
            vulnerable_signals=tuple(sorted(set(vulnerable_signals))),
            secure_signals=tuple(sorted(set(secure_signals))),
            inconclusive_signals=tuple(sorted(set(inconclusive_signals))),
            evidence=tuple(item.to_evidence() for item in outcomes),
            meta={
                "laboratory": LABORATORY_ID,
                "base_url": base_url,
                "probes_total": len(outcomes),
                "probes_reachable": len(reachable),
                "rule_matches": matched_total,
                "redaction": "enforced",
            },
        )


def build_adapter(request: ExecutionRequest, runner: CommandRunner | None = None):
    """Return the adapter calibrated for ``request``.

    Raises :class:`NotImplementedError` with an explicit message for handlers
    that are declared but not calibrated yet.
    """

    provider, action = request.handler
    if (provider, action) == ("secrets", "scan") and request.target_ref == LABORATORY_ID:
        return WrongSecretsAdapter(runner=runner or LocalCommandRunner())
    raise NotImplementedError(
        f"handler {provider}/{action} has no calibrated adapter for target {request.target_ref!r}"
    )
