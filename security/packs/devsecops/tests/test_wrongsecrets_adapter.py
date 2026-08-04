"""Adapter and sanitisation tests using a fake command runner (no network)."""

from __future__ import annotations

from dataclasses import dataclass, field

from devsecops_runbooks.adapters.wrongsecrets import (
    PROBE_PATHS,
    WrongSecretsAdapter,
    detect_rules,
)
from devsecops_runbooks.contracts import Decision, ExecutionRequest, Status
from devsecops_runbooks.execution import (
    CommandError,
    CommandResult,
    build_http_probe,
    parse_http_status,
)
from devsecops_runbooks.sanitizer import REDACTED, sanitize_mapping, sanitize_text

LEAKED = "password=SuperSecret123"  # noqa: S105 - synthetic test fixture


def make_request(**overrides) -> ExecutionRequest:
    payload = {
        "provider": "secrets",
        "action": "scan",
        "profile": "wrongsecrets-exposure",
        "target_ref": "wrongsecrets",
        "scope": "laboratory",
        "arguments": {"base_url": "http://wrongsecrets:8080"},
    }
    payload.update(overrides)
    return ExecutionRequest.from_payload(payload)


@dataclass
class FakeRunner:
    """Deterministic stand-in for :class:`LocalCommandRunner`."""

    bodies: dict[str, tuple[int | None, str]] = field(default_factory=dict)
    default: tuple[int | None, str] = (404, "")
    raises: bool = False
    calls: list[list[str]] = field(default_factory=list)

    def run(self, argv, timeout=None):
        self.calls.append(list(argv))
        if self.raises:
            raise CommandError("binary 'curl' is not available on this host")
        url = argv[-1]
        status, body = next(
            ((s, b) for path, (s, b) in self.bodies.items() if url.endswith(path)),
            self.default,
        )
        if status is None:
            return CommandResult(tuple(argv), 7, "\n__HTTP_STATUS__:000", "connection refused")
        return CommandResult(tuple(argv), 0, f"{body}\n__HTTP_STATUS__:{status}", "")


def test_probe_command_is_read_only_and_allowlisted():
    argv = build_http_probe("http://wrongsecrets:8080", "/actuator/health")
    assert argv[0] == "curl"
    assert "--get" in argv
    assert argv[-1] == "http://wrongsecrets:8080/actuator/health"
    assert not any(token in argv for token in (";", "&&", "|"))


def test_probe_budget_covers_the_landing_page():
    # The WrongSecrets landing page is ~85 KiB; a smaller --max-filesize makes
    # curl exit 63 and the surface would be misreported as unreachable.
    from devsecops_runbooks.adapters.wrongsecrets import PROBE_MAX_BYTES, WrongSecretsAdapter

    assert PROBE_MAX_BYTES >= 131072
    argv = WrongSecretsAdapter(runner=FakeRunner()).probe("application-root", "/").command
    assert argv["exit_code"] == 0


def test_probe_rejects_non_http_and_relative_paths():
    for base, path in (("file:///etc", "/x"), ("http://a", "no-slash")):
        try:
            build_http_probe(base, path)
        except CommandError:
            continue
        raise AssertionError(f"expected CommandError for {base}{path}")


def test_parse_http_status_splits_marker():
    assert parse_http_status("body\n__HTTP_STATUS__:200") == (200, "body")
    assert parse_http_status("no marker") == (None, "no marker")


def test_parse_http_status_treats_curl_000_as_unreachable():
    # curl emits 000 when no HTTP response was ever received.
    assert parse_http_status("\n__HTTP_STATUS__:000") == (None, "")


def test_adapter_marks_probe_unreachable_on_nonzero_curl_exit():
    @dataclass
    class FailingRunner:
        def run(self, argv, timeout=None):
            return CommandResult(tuple(argv), 7, "\n__HTTP_STATUS__:000", "connection refused")

    result = WrongSecretsAdapter(runner=FailingRunner()).run(make_request())
    assert result.decision is Decision.INCONCLUSIVE
    assert "target.unreachable" in result.inconclusive_signals
    assert result.meta["probes_reachable"] == 0


def test_detect_rules_reports_ids_only():
    rules = detect_rules("AKIAIOSFODNN7EXAMPLE and " + LEAKED)
    assert "aws-access-key-id" in rules
    assert "credential-assignment" in rules
    assert all(isinstance(rule, str) for rule in rules)
    assert "AKIAIOSFODNN7EXAMPLE" not in " ".join(rules)


def test_adapter_returns_vulnerable_on_exposed_secret():
    runner = FakeRunner(
        bodies={
            "/actuator/health": (200, '{"status":"UP"}'),
            "/": (200, "welcome"),
            "/challenge/challenge-1": (200, LEAKED),
            "/spoil/challenge-1": (200, "<div class='spoiler'>synthetic-answer-value</div>"),
            "/actuator/env": (200, "«redacted:AKIA…»"),
        }
    )
    result = WrongSecretsAdapter(runner=runner).run(make_request())
    assert result.status is Status.OK
    assert result.decision is Decision.VULNERABLE
    assert any(signal.startswith("secret.exposed") for signal in result.vulnerable_signals)
    assert "actuator.exposed:configuration-surface" in result.vulnerable_signals
    assert "secret.answer_disclosed:challenge-spoiler" in result.vulnerable_signals
    assert result.meta["probes_reachable"] == len(PROBE_PATHS)


def test_adapter_returns_secure_when_no_exposure():
    runner = FakeRunner(
        bodies={
            "/actuator/health": (200, '{"status":"UP"}'),
            "/": (200, "welcome"),
            "/challenge/challenge-1": (200, "solve the challenge"),
            "/spoil/challenge-1": (404, "not found"),
            "/actuator/env": (403, ""),
        }
    )
    result = WrongSecretsAdapter(runner=runner).run(make_request())
    assert result.decision is Decision.SECURE
    assert "secret.no_exposure_detected" in result.secure_signals
    assert "actuator.protected:configuration-surface" in result.secure_signals
    assert "spoiler.protected:challenge-spoiler" in result.secure_signals


def test_adapter_is_inconclusive_when_target_unreachable():
    result = WrongSecretsAdapter(runner=FakeRunner(default=(None, ""))).run(make_request())
    assert result.status is Status.OK
    assert result.decision is Decision.INCONCLUSIVE
    assert "target.unreachable" in result.inconclusive_signals


def test_adapter_never_emits_secret_material():
    runner = FakeRunner(
        bodies={
            "/actuator/health": (200, "UP"),
            "/": (200, LEAKED),
            "/challenge/challenge-1": (200, "«redacted:ghp_…»"),
            "/spoil/challenge-1": (200, "<div class='spoiler'>synthetic-answer-value</div>"),
            "/actuator/env": (200, "-----BEGIN RSA PRIVATE KEY-----"),
        }
    )
    result = WrongSecretsAdapter(runner=runner).run(make_request())
    blob = repr(result.to_dict())
    assert "SuperSecret123" not in blob
    assert "ghp_abcdefghijklmnopqrstuvwxyz012345" not in blob
    assert result.decision is Decision.VULNERABLE


def test_sanitize_text_redacts_known_shapes():
    assert "SuperSecret123" not in sanitize_text(LEAKED)
    assert REDACTED in sanitize_text("Authorization: Bearer abc.def-123")
    assert REDACTED in sanitize_text("AKIAIOSFODNN7EXAMPLE")
    assert REDACTED in sanitize_text("WRONGSECRETS_SYNTHETIC_MARKER")


def test_sanitize_mapping_redacts_sensitive_keys_recursively():
    data = {"api_key": "abc", "nested": {"Password": "x", "count": 3}, "items": [LEAKED]}
    cleaned = sanitize_mapping(data)
    assert cleaned["api_key"] == REDACTED
    assert cleaned["nested"]["Password"] == REDACTED
    assert cleaned["nested"]["count"] == 3
    assert "SuperSecret123" not in str(cleaned["items"])


def test_sanitize_text_is_bounded_and_deterministic():
    long_text = "a" * 20000
    first = sanitize_text(long_text)
    assert first == sanitize_text(long_text)
    assert len(first.encode()) < 20000


def test_adapter_reports_error_when_binary_missing():
    result = WrongSecretsAdapter(runner=FakeRunner(raises=True)).run(make_request())
    assert result.decision is Decision.INCONCLUSIVE
    assert "target.unreachable" in result.inconclusive_signals
