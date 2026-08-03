import pytest

from api_pentest_runbooks.policy import PolicyViolation, authorise, validate_target


def test_target_must_be_allowlisted():
    policy = {"scope": {"allowed_hosts": ["crapi"], "allowed_cidrs": []}}
    validate_target({"base_url": "http://crapi:8888"}, policy)
    with pytest.raises(PolicyViolation):
        validate_target({"base_url": "http://example.com"}, policy)


def test_production_blocks_non_safe_runbook():
    runbook = {"risk": {"intrusiveness": "low", "production_safe": False, "destructive": False}}
    policy = {"environment": "production", "execution": {"allowed_intrusiveness": ["low"], "allow_destructive": False}}
    with pytest.raises(PolicyViolation):
        authorise(runbook, policy)


def test_destructive_is_blocked_by_default():
    runbook = {"risk": {"intrusiveness": "medium", "production_safe": False, "destructive": True}}
    policy = {"environment": "laboratory", "execution": {"allowed_intrusiveness": ["medium"], "allow_destructive": False}}
    with pytest.raises(PolicyViolation):
        authorise(runbook, policy)
