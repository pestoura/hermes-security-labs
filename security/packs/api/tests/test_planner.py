from pathlib import Path

from api_pentest_runbooks.catalog import load_runbooks, load_yaml
from api_pentest_runbooks.planner import plan

ROOT = Path(__file__).resolve().parents[1]


def test_graphql_campaign_selects_only_applicable_graphql_profiles():
    runbooks = load_runbooks(ROOT / "runbooks")
    campaign = load_yaml(ROOT / "campaigns/graphql.yaml")
    target = {"api_type": "graphql", "auth_type": "none", "capabilities": ["graphql"]}
    selected = plan(runbooks, campaign, target)
    assert {item["metadata"]["id"] for item in selected} == {
        "API-DISC-GRAPHQL-ENDPOINT-008",
        "API-DISC-GRAPHQL-INTROSPECTION-009",
        "API-INPUT-GRAPHQL-INJECTION-020",
        "API-INPUT-GRAPHQL-BATCH-021",
        "API-INPUT-GRAPHQL-ALIAS-022",
        "API-RATE-GRAPHQL-DEPTH-009",
    }
