from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_chg096_evidence_records_reconciled_foundation_milestone():
    p = ROOT / 'roadmap/reconciliation/foundation-milestone-accounting-CHG-HSL-096.yaml'
    data = yaml.safe_load(p.read_text())
    assert data['change_record'] == 'CHG-HSL-096'
    assert data['milestone'] == {'number': 1, 'title': 'SVP v2 Foundation'}
    assert data['before']['state'] == 'open'
    assert data['before']['open_issues'] == 2
    assert data['before']['closed_issues'] == 2
    assert data['after']['state'] == 'closed'
    assert data['after']['open_issues'] == 0
    assert data['after']['closed_issues'] == 4
    assert data['after']['issues'] == [76, 77, 78, 80]
    assert data['runtime_change'] is False


def test_lane_b_marks_foundation_accounting_resolved():
    text = (ROOT / 'docs/roadmap/lane-b-cross-cutting-reconciliation.md').read_text()
    assert 'Close the milestone accounting gap on `SVP v2 Foundation` | 1 | no | **DELIVERED by CHG-HSL-096**' in text
    assert 'Milestone `SVP v2 Foundation` accounting gap is resolved' in text
    assert 'open_issues=0' in text
    assert 'closed_issues=4' in text


def test_chg096_change_record_exists_and_is_doc_only():
    data = yaml.safe_load((ROOT / 'changes/CHG-HSL-096.yaml').read_text())
    assert data['id'] == 'CHG-HSL-096'
    assert data['classification'] == 'DOC_ONLY'
    assert data['validation']['targeted'] == 'PASS'
    assert data['validation']['runtime'] == 'NOT_RUN'
