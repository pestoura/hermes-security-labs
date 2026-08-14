"""Repository-only governance tests for JDS-002 change-record consistency.

Pin the source-of-truth contract between change records under ``changes/`` and
the canonical validation campaign ``validation/VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml``.

Every accepted change record that declares a ``source.observation`` must point at
an observation that actually exists in the campaign. A dangling reference (a
change record citing an undefined observation id) is a source-of-truth
inconsistency and must fail closed: it must never be silently tolerated.

No runtime, policy, trust-store or promotion semantics are asserted here. This is
a static ledger/reconciliation guard only.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CHANGES_DIR = ROOT / "changes"
CAMPAIGN_PATH = ROOT / "validation" / "VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml"


def _campaign_observation_ids() -> frozenset[str]:
    document = yaml.safe_load(CAMPAIGN_PATH.read_text(encoding="utf-8"))
    observations = document.get("observations") or []
    return frozenset(
        str(observation["id"])
        for observation in observations
        if isinstance(observation, dict) and observation.get("id")
    )


def _accepted_change_records() -> list[dict]:
    records: list[dict] = []
    for path in sorted(CHANGES_DIR.glob("CHG-HSL-*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            continue
        records.append(document)
    return records


def test_campaign_defines_known_observations() -> None:
    ids = _campaign_observation_ids()
    # The four inspected promotion observations plus the resolved repository chain.
    for required in (
        "OBS-RUNNER-REPO-CHAIN",
        "OBS-TB1-LIVE-DELIVERY",
        "OBS-RUNNER-POLICY-PROMOTION",
        "OBS-EVIDENCE-CUSTODY",
        "OBS-LIVE-EFFECT-RESET",
    ):
        assert required in ids, f"canonical campaign is missing observation {required}"


def test_change_records_reference_only_defined_observations() -> None:
    known = _campaign_observation_ids()
    dangling: list[tuple[str, str]] = []
    for record in _accepted_change_records():
        source = record.get("source") or {}
        observation = source.get("observation")
        if observation is None:
            continue
        if observation not in known:
            dangling.append((str(record.get("id")), str(observation)))
    assert not dangling, f"change records reference undefined observations: {dangling}"


def test_chg_hsl_034_points_at_defined_observation() -> None:
    document = yaml.safe_load(
        (CHANGES_DIR / "CHG-HSL-034.yaml").read_text(encoding="utf-8")
    )
    assert document["source"]["observation"] in _campaign_observation_ids()
