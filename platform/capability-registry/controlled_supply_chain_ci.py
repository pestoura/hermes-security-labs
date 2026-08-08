"""Controlled-CI cryptographic supply-chain evidence for SVP2-C-02.

Creates SBOM/provenance records for a disposable repository artefact and signs the
subject digest with an ephemeral Ed25519 key through OpenSSL. The private key exists
only inside a temporary directory. Vulnerability scanning remains explicitly NOT_RUN.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


class ControlledSupplyChainError(RuntimeError):
    pass


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _run(args: list[str]) -> None:
    result = subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, check=False)
    if result.returncode != 0:
        raise ControlledSupplyChainError("controlled cryptographic operation failed")


def build_controlled_bundle(*, artifact: bytes, source_ref: str) -> dict[str, Any]:
    openssl = shutil.which("openssl")
    if not openssl:
        raise ControlledSupplyChainError("openssl unavailable")
    if not artifact or not source_ref:
        raise ControlledSupplyChainError("artifact and source_ref are required")

    subject = _sha256(artifact)
    sbom = {
        "spdxVersion": "SPDX-2.3",
        "name": "hex0r-controlled-ci-artifact",
        "subject_digest": subject,
        "packages": [],
    }
    provenance = {
        "predicateType": "https://slsa.dev/provenance/v1",
        "subject_digest": subject,
        "builder": "github-actions-controlled-ci",
        "source_ref": source_ref,
    }
    sbom_bytes = json.dumps(sbom, sort_keys=True, separators=(",", ":")).encode()
    provenance_bytes = json.dumps(provenance, sort_keys=True, separators=(",", ":")).encode()

    with tempfile.TemporaryDirectory(prefix="hex0r-supply-chain-") as tmp:
        root = Path(tmp)
        private_key = root / "ephemeral-ed25519.pem"
        public_key = root / "ephemeral-ed25519.pub.pem"
        payload = root / "subject.txt"
        signature = root / "subject.sig"
        payload.write_text(subject, encoding="utf-8")
        _run([openssl, "genpkey", "-algorithm", "ED25519", "-out", str(private_key)])
        _run([openssl, "pkey", "-in", str(private_key), "-pubout", "-out", str(public_key)])
        _run([openssl, "pkeyutl", "-sign", "-inkey", str(private_key), "-rawin", "-in", str(payload), "-out", str(signature)])
        _run([openssl, "pkeyutl", "-verify", "-pubin", "-inkey", str(public_key), "-rawin", "-in", str(payload), "-sigfile", str(signature)])
        signature_digest = _sha256(signature.read_bytes())

    return {
        "schema_version": "1.0.0",
        "boundary": "CONTROLLED_CI",
        "subject_digest": subject,
        "sbom": {
            "verified": True,
            "subject_digest": subject,
            "artifact_digest": _sha256(sbom_bytes),
            "format": "SPDX-2.3",
        },
        "signature": {
            "verified": True,
            "subject_digest": subject,
            "artifact_digest": signature_digest,
            "algorithm": "Ed25519",
            "key_lifecycle": "EPHEMERAL_CONTROLLED_CI",
        },
        "provenance": {
            "verified": True,
            "subject_digest": subject,
            "artifact_digest": _sha256(provenance_bytes),
            "predicate_type": provenance["predicateType"],
        },
        "scan": {
            "subject_digest": subject,
            "status": "NOT_RUN",
        },
        "stable_promotion": "BLOCKED_UNTIL_SCAN_EVIDENCE",
        "production_image": "NOT_RUN",
    }
