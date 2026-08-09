from __future__ import annotations

import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "deployment" / "private-ghcr-vampi-acceptance.sh"
LIFECYCLE = ROOT / "platform" / "environments" / "web-api" / "vampi" / "scripts" / "lifecycle.sh"
PRIVATE_DIGEST = "sha256:b1b66324a2d35cfe55e3edcd81f9f3c012907c71367df37f83d9ef63b500b3d3"


def test_private_ghcr_acceptance_plan_is_non_secret_and_non_mutating() -> None:
    result = subprocess.run(
        ["bash", str(HARNESS), "plan"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    assert "ISSUE53_PRIVATE_GHCR_ACCEPTANCE_PLAN" in result.stdout
    assert "Gate F:" in result.stdout
    assert "Gate G:" in result.stdout
    assert "Gate H:" in result.stdout
    assert PRIVATE_DIGEST in result.stdout
    assert "temporary-public or private" in result.stdout
    assert "Versioned Compose mutation: none" in result.stdout
    assert "Package mutation: none" in result.stdout
    assert "strict (default) requires exactly read:packages" in result.stdout
    assert "DEGRADED_ACCEPTED_FOR_DEV" in result.stdout


def _extract_scope_snippet() -> str:
    source = HARNESS.read_text()
    start = source.index('scope_result="$(python3 - "${scopes}" "${scope_mode}" <<\'PY\'')
    body = source[start:]
    body = body[body.index("\n") + 1 :]
    return body[: body.index("\nPY\n")]


def _eval_scope(scopes: str, mode: str) -> tuple[int, str]:
    result = subprocess.run(
        ["python3", "-c", _extract_scope_snippet(), scopes, mode],
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode, result.stdout.strip()


def test_strict_scope_mode_requires_exactly_read_packages() -> None:
    assert _eval_scope("read:packages", "strict") == (0, "PASS_EXACT")
    assert _eval_scope("read:packages, repo", "strict")[0] != 0
    assert _eval_scope("repo", "strict")[0] != 0


def test_dev_scope_mode_accepts_additional_scopes_but_requires_read_packages() -> None:
    assert _eval_scope("read:packages", "dev") == (0, "PASS_EXACT")
    assert _eval_scope("repo, write:org, read:packages", "dev") == (0, "PASS_DEGRADED")
    assert _eval_scope("repo, write:org", "dev")[0] != 0


def test_dev_scope_mode_accepts_parent_scopes_that_imply_package_read() -> None:
    assert _eval_scope("repo, write:packages", "dev") == (0, "PASS_DEGRADED")
    assert _eval_scope("repo, delete:packages", "dev") == (0, "PASS_DEGRADED")
    assert _eval_scope("repo, write:packages", "strict")[0] != 0


def test_invalid_scope_mode_is_rejected_before_token_read() -> None:
    result = subprocess.run(
        [
            "bash",
            str(HARNESS),
            "accept",
            "--scope-mode",
            "loose",
            "--username",
            "example",
            "--approval-ref",
            "approval-test",
            "--publisher-visibility",
            "private",
            "--package-private-confirmed",
            "--package-access-confirmed",
        ],
        cwd=ROOT,
        input="must-not-be-consumed\n",
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert "scope mode must be strict or dev" in result.stdout


def test_dev_mode_records_degraded_posture_without_least_privilege_claim() -> None:
    source = HARNESS.read_text()
    assert "scope_posture=DEGRADED_ACCEPTED_FOR_DEV" in source
    assert "least_privilege_claimed=false" in source
    assert "production_closure_blocked_until_read_packages_only=true" in source
    assert "PASS_AUTHORITY_SUFFICIENT_NO_MUTATION_ATTEMPTED" in source
    assert 'scope_mode="strict"' in source


def test_acceptance_fails_before_token_read_without_manual_gates() -> None:
    result = subprocess.run(
        ["bash", str(HARNESS), "accept"],
        cwd=ROOT,
        input="must-not-be-consumed\n",
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert "publisher visibility must be explicitly confirmed" in result.stdout


def test_harness_never_uses_mutating_registry_commands_or_token_arguments() -> None:
    source = HARNESS.read_text()
    lowered = source.lower()
    assert "--password-stdin" in source
    assert "read:packages" in source
    assert "X-OAuth-Scopes" in source
    assert "--publisher-visibility <temporary-public|private>" in source
    assert "--package-private-confirmed" in source
    assert "--package-access-confirmed" in source
    assert "write:packages" not in source.replace(
        '    implying = {"read:packages", "write:packages", "delete:packages"}\n', ""
    ).replace(
        "    # granted; `write:packages` and `delete:packages` both imply read.\n", ""
    )
    assert "delete:packages" not in source.replace(
        '    implying = {"read:packages", "write:packages", "delete:packages"}\n', ""
    ).replace(
        "    # granted; `write:packages` and `delete:packages` both imply read.\n", ""
    )
    assert "pull,push" not in source
    assert "scope=repository:" not in source
    assert "docker push" not in lowered
    assert "manifest push" not in lowered
    assert "docker buildx build --push" not in lowered
    assert "curl -x delete" not in lowered
    assert "curl --request delete" not in lowered
    assert "ghcr_pat=" not in lowered
    assert "export ghcr_pat" not in lowered
    assert "credential_source=stdin" in source
    assert "credential_value_recorded=false" in source
    assert "gate_g_registry_mutation_attempted=false" in source
    assert PRIVATE_DIGEST in source


def test_vampi_lifecycle_refuses_override_outside_runtime(tmp_path: Path) -> None:
    override = tmp_path / "outside-runtime.yaml"
    override.write_text("services:\n  vampi:\n    image: example.invalid/ref@sha256:" + "0" * 64 + "\n")
    env = os.environ.copy()
    env["VAMPI_COMPOSE_OVERRIDE"] = str(override)
    result = subprocess.run(
        ["bash", str(LIFECYCLE), "status"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Refusing override outside" in result.stderr


def test_runtime_override_is_bounded_and_symlinks_are_forbidden() -> None:
    source = LIFECYCLE.read_text()
    assert "VAMPI_COMPOSE_OVERRIDE" in source
    assert '${REPO_ROOT}/.runtime' in source
    assert "Symlink overrides are forbidden" in source
    assert 'COMPOSE+=(-f "${override_real}")' in source
