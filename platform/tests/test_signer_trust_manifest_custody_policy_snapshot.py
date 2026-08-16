from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "platform" / "evidence-plane" / "signer_trust_manifest_custody.py"
POLICY_PATH = ROOT / "platform" / "evidence-plane" / "signer-trust-manifest-custody-policy.yaml"


def _load():
    resolved = MODULE_PATH.resolve()
    for module in tuple(sys.modules.values()):
        module_file = getattr(module, "__file__", None)
        if module_file and Path(module_file).resolve() == resolved:
            return module
    spec = importlib.util.spec_from_file_location("chg_hsl_077_policy_snapshot", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_validated_policy_is_snapshotted_deeply_at_construction() -> None:
    custody = _load()
    supplied = custody.load_policy(POLICY_PATH)
    supplied["state"] = "ENABLED"
    bridge = custody.SignerTrustManifestCustody(supplied)

    # Mutating caller-owned nested policy state after validation must not alter
    # the bridge's already-validated policy snapshot.
    supplied["custody"]["classification"] = "summary"
    supplied["custody"]["retention_days"] = 999
    supplied["custody"]["install_trust"] = True

    assert bridge._policy["custody"]["classification"] == "restricted"
    assert bridge._policy["custody"]["retention_days"] == 30
    assert bridge._policy["custody"]["install_trust"] is False
