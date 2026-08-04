import base64
import json
import shlex

from api_pentest_runbooks.adapter import RUNNER_PATH, build_mcp_call


def test_mcp_call_uses_fixed_runner_and_encoded_payload():
    request = {"handler": "http", "arguments": {"url": "http://crapi:8888"}}
    call = build_mcp_call(request)
    assert call["tool"] == "execute_command"
    command = call["arguments"]["command"]
    parts = shlex.split(command)
    assert parts[:3] == ["python3", RUNNER_PATH, "execute"]
    assert parts[3] == "--payload-b64"
    decoded = json.loads(base64.urlsafe_b64decode(parts[4].encode()))
    assert decoded == request
    assert ";" not in command
