"""Semantic contract tests for JWT/TLS dotted signal aliases (issue #64 campaign-1).

Campaign manifest evidence:
`artifacts/issue64-final/campaign-1/manifest.json` reported
`evaluator_error: unknown signals: jwt.alg, jwt.claims.aud, jwt.claims.exp,
jwt.claims.iss, jwt.claims.sub, jwt.secret_bits, jwt.signature.valid,
tls.cert_expired, tls.hostname_mismatch, tls.plaintext_allowed, tls.weak_ciphers`.

All eleven names have canonical equivalents already present in the signal
catalog, so they are remapped as aliases. No new signal vocabulary is added and
genuinely unknown signals must keep failing.
"""

from __future__ import annotations

import pytest

from evaluation import (
    SIGNAL_ALIASES,
    SignalError,
    canonicalize_signals,
    evaluate_signals,
    load_signal_catalog,
    normalize_execution_output,
)

MANIFEST_SIGNALS = (
    "jwt.alg",
    "jwt.claims.aud",
    "jwt.claims.exp",
    "jwt.claims.iss",
    "jwt.claims.sub",
    "jwt.secret_bits",
    "jwt.signature.valid",
    "tls.cert_expired",
    "tls.hostname_mismatch",
    "tls.plaintext_allowed",
    "tls.weak_ciphers",
)


class TestAliasContract:
    @pytest.mark.parametrize("alias", MANIFEST_SIGNALS)
    def test_alias_is_declared(self, alias: str) -> None:
        assert alias in SIGNAL_ALIASES

    @pytest.mark.parametrize("alias", MANIFEST_SIGNALS)
    def test_alias_target_exists_in_catalog(self, alias: str) -> None:
        assert SIGNAL_ALIASES[alias] in load_signal_catalog()

    def test_canonicalize_remaps_without_inventing_signals(self) -> None:
        canonical = canonicalize_signals({"jwt.alg": "none", "response_status": 200})
        assert canonical == {"jwt_alg": "none", "response_status": 200}


class TestJwtAliasesAccepted:
    def test_jwt_alias_signals_evaluate_vulnerable(self) -> None:
        result = evaluate_signals(
            {
                "jwt.alg": "none",
                "jwt.signature.valid": False,
                "jwt.secret_bits": 32,
                "jwt.claims.aud": "other",
                "jwt.claims.iss": "attacker",
                "jwt.claims.sub": "victim",
                "jwt.claims.exp": 0,
                "target_reachable": True,
                "prerequisites_missing": False,
            },
            {
                "vulnerable_when": ["jwt.alg == 'none' or jwt.signature.valid == false"],
                "secure_when": ["jwt.signature.valid == true and jwt.alg != 'none'"],
                "inconclusive_when": ["target_reachable == false"],
            },
        )
        assert result.decision == "vulnerable"

    def test_jwt_alias_signals_evaluate_secure(self) -> None:
        result = evaluate_signals(
            {
                "jwt.alg": "RS256",
                "jwt.signature.valid": True,
                "jwt.secret_bits": 256,
                "target_reachable": True,
                "prerequisites_missing": False,
            },
            {
                "vulnerable_when": ["jwt.alg == 'none' or jwt.signature.valid == false"],
                "secure_when": ["jwt.signature.valid == true and jwt.alg != 'none'"],
                "inconclusive_when": ["target_reachable == false"],
            },
        )
        assert result.decision == "secure"

    def test_canonical_criteria_accept_alias_signals(self) -> None:
        result = evaluate_signals(
            {"jwt.secret_bits": 64, "target_reachable": True, "prerequisites_missing": False},
            {
                "vulnerable_when": ["jwt_secret_bits == 64"],
                "secure_when": [],
                "inconclusive_when": [],
            },
        )
        assert result.decision == "vulnerable"


class TestTlsAliasesAccepted:
    def test_tls_alias_signals_evaluate_vulnerable(self) -> None:
        result = evaluate_signals(
            {
                "tls.cert_expired": True,
                "tls.hostname_mismatch": False,
                "tls.weak_ciphers": False,
                "tls.plaintext_allowed": False,
                "target_reachable": True,
                "prerequisites_missing": False,
            },
            {
                "vulnerable_when": [
                    (
                        "tls.cert_expired == true or tls.hostname_mismatch == true "
                        "or tls.weak_ciphers == true or tls.plaintext_allowed == true"
                    )
                ],
                "secure_when": ["tls.cert_expired == false and tls.plaintext_allowed == false"],
                "inconclusive_when": ["target_reachable == false"],
            },
        )
        assert result.decision == "vulnerable"

    def test_tls_alias_signals_evaluate_secure(self) -> None:
        result = evaluate_signals(
            {
                "tls.cert_expired": False,
                "tls.hostname_mismatch": False,
                "tls.weak_ciphers": False,
                "tls.plaintext_allowed": False,
                "target_reachable": True,
                "prerequisites_missing": False,
            },
            {
                "vulnerable_when": [
                    (
                        "tls.cert_expired == true or tls.hostname_mismatch == true "
                        "or tls.weak_ciphers == true or tls.plaintext_allowed == true"
                    )
                ],
                "secure_when": ["tls.cert_expired == false and tls.plaintext_allowed == false"],
                "inconclusive_when": ["target_reachable == false"],
            },
        )
        assert result.decision == "secure"

    def test_normalized_tls_output_is_accepted_by_evaluator(self) -> None:
        signals = normalize_execution_output(
            "tls",
            {"cert_expired": True, "hostname_mismatch": False, "weak_ciphers": True, "plaintext_allowed": False},
        )
        result = evaluate_signals(
            signals,
            {
                "vulnerable_when": ["tls.cert_expired == true or tls.weak_ciphers == true"],
                "secure_when": [],
                "inconclusive_when": [],
            },
        )
        assert result.decision == "vulnerable"


class TestNegativeControls:
    def test_runner_metadata_still_filtered_and_rejected(self) -> None:
        functional = normalize_execution_output(
            "http",
            {"status": "ok", "response_status": 200, "runner_exit_code": 0, "runner_status": "ok", "runner_stdout": "x"},
        )
        assert {"runner_exit_code", "runner_status", "runner_stdout"}.isdisjoint(functional)
        with pytest.raises(SignalError):
            evaluate_signals(
                {"response_status": 200, "runner_exit_code": 0},
                {"vulnerable_when": ["response_status == 200"], "secure_when": [], "inconclusive_when": []},
            )

    def test_invented_signal_still_rejected(self) -> None:
        with pytest.raises(SignalError) as excinfo:
            evaluate_signals(
                {"jwt.totally_made_up": True},
                {"vulnerable_when": ["response_status == 200"], "secure_when": [], "inconclusive_when": []},
            )
        assert "unknown signals" in str(excinfo.value)

    def test_invented_tls_signal_still_rejected(self) -> None:
        with pytest.raises(SignalError):
            evaluate_signals(
                {"tls.quantum_safe": False},
                {"vulnerable_when": ["tls_cert_expired == true"], "secure_when": [], "inconclusive_when": []},
            )

    def test_alias_does_not_widen_catalog(self) -> None:
        catalog = load_signal_catalog()
        for alias in SIGNAL_ALIASES:
            assert alias not in catalog
