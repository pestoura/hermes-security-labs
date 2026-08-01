#!/usr/bin/env python3
"""Sanitised acceptance harness for OWASP WrongSecrets Challenge 3.

The harness retrieves ``DOCKER_ENV_PASSWORD`` from the owned target container,
keeps it in process memory, establishes a normal web session, obtains the CSRF
token and submits the answer to the canonical Challenge 3 route. It emits only
boolean/sanitised metadata and never prints or persists the challenge value.

Upstream contract pinned by this laboratory:
- OWASP/wrongsecrets commit 2fbf78532886135c3448c238f48ffd5b0e81f7e9
- short name: challenge-3
- route: /challenge/challenge-3
- form fields: action=submit, solution=<in-memory value>, _csrf=<session token>
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Final, NoReturn

PROJECT_NAME: Final = "wrongsecrets"
TARGET_SERVICE: Final = "wrongsecrets"
CHALLENGE_PATH: Final = "/challenge/challenge-3"
ENVIRONMENT_KEY: Final = "DOCKER_ENV_PASSWORD"
SUCCESS_MARKER: Final = "Your answer is correct!"
DEFAULT_HOST_PORT: Final = 8082
HTTP_TIMEOUT_SECONDS: Final = 10


class SanitisedFailure(RuntimeError):
    """Failure carrying only a public, non-sensitive diagnostic code."""


class CsrfTokenParser(HTMLParser):
    """Extract the Spring Security CSRF token without retaining the page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.token: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "input" or self.token is not None:
            return
        attributes = dict(attrs)
        if attributes.get("name") == "_csrf" and attributes.get("value"):
            self.token = attributes["value"]


def _fail(code: str) -> NoReturn:
    raise SanitisedFailure(code)


def _run_command(arguments: list[str]) -> bytes:
    try:
        completed = subprocess.run(
            arguments,
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=HTTP_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        _fail("required-command-unavailable")
    except subprocess.TimeoutExpired:
        _fail("local-command-timeout")
    except subprocess.CalledProcessError:
        _fail("local-command-failed")
    return completed.stdout


def _compose_file() -> Path:
    return Path(__file__).resolve().parent.parent / "compose.yaml"


def _target_container_id() -> str:
    output = _run_command(
        [
            "docker",
            "compose",
            "--project-name",
            PROJECT_NAME,
            "--file",
            str(_compose_file()),
            "ps",
            "--quiet",
            TARGET_SERVICE,
        ]
    )
    container_ids = [line.strip() for line in output.decode("ascii", errors="strict").splitlines() if line.strip()]
    if len(container_ids) != 1:
        _fail("target-container-not-unique")
    return container_ids[0]


def _challenge_value_from_container(container_id: str) -> str:
    raw_environment = _run_command(
        [
            "docker",
            "inspect",
            "--format",
            "{{json .Config.Env}}",
            container_id,
        ]
    )
    try:
        environment = json.loads(raw_environment.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        _fail("target-environment-unreadable")
    if not isinstance(environment, list):
        _fail("target-environment-invalid")

    prefix = f"{ENVIRONMENT_KEY}="
    matches = [entry[len(prefix) :] for entry in environment if isinstance(entry, str) and entry.startswith(prefix)]
    if len(matches) != 1 or not matches[0]:
        _fail("challenge-value-not-available")
    return matches[0]


def _host_port() -> int:
    configured = os.environ.get("WRONGSECRETS_HOST_PORT", str(DEFAULT_HOST_PORT))
    try:
        port = int(configured, 10)
    except ValueError:
        _fail("invalid-host-port")
    if port < 1 or port > 65535:
        _fail("invalid-host-port")
    return port


def _csrf_token(page: str) -> str:
    parser = CsrfTokenParser()
    parser.feed(page)
    parser.close()
    if not parser.token:
        _fail("csrf-token-not-found")
    return parser.token


def _response_is_success(status: int, page: str) -> bool:
    return status == 200 and SUCCESS_MARKER in page and "answer is incorrect" not in page.lower()


def _exercise(base_url: str, challenge_value: str) -> int:
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    challenge_url = urllib.parse.urljoin(base_url, CHALLENGE_PATH)

    try:
        with opener.open(challenge_url, timeout=HTTP_TIMEOUT_SECONDS) as response:
            get_status = response.status
            challenge_page = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        _fail(f"challenge-get-http-{error.code}")
    except (urllib.error.URLError, TimeoutError):
        _fail("challenge-get-unavailable")

    if get_status != 200:
        _fail(f"challenge-get-http-{get_status}")

    csrf_token = _csrf_token(challenge_page)
    form_body = urllib.parse.urlencode(
        {
            "action": "submit",
            "solution": challenge_value,
            "_csrf": csrf_token,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        challenge_url,
        data=form_body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    try:
        with opener.open(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            post_status = response.status
            result_page = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        _fail(f"challenge-post-http-{error.code}")
    except (urllib.error.URLError, TimeoutError):
        _fail("challenge-post-unavailable")

    if not _response_is_success(post_status, result_page):
        _fail("challenge-answer-not-accepted")
    return post_status


def _self_test() -> int:
    synthetic_value = "SELF_TEST_VALUE_MUST_NOT_APPEAR"
    sample_page = '<html><input type="hidden" name="_csrf" value="csrf-test-token"></html>'
    if _csrf_token(sample_page) != "csrf-test-token":
        _fail("self-test-csrf-parser")
    if CHALLENGE_PATH != "/challenge/challenge-3":
        _fail("self-test-canonical-route")
    if not _response_is_success(200, f"<p>{SUCCESS_MARKER}</p>"):
        _fail("self-test-success-classifier")
    if _response_is_success(404, f"<p>{SUCCESS_MARKER}</p>"):
        _fail("self-test-status-classifier")

    public_output = "Challenge 3 exercise: PASS — value processed in memory and not disclosed"
    if synthetic_value in public_output:
        _fail("self-test-output-sanitisation")
    print("WRONGSECRETS_CHALLENGE3_HARNESS_SELF_TEST_OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the sanitised WrongSecrets Challenge 3 acceptance gate.")
    parser.add_argument("--self-test", action="store_true", help="Run deterministic tests without Docker or HTTP.")
    arguments = parser.parse_args()

    if arguments.self_test:
        try:
            return _self_test()
        except SanitisedFailure as error:
            print(f"WRONGSECRETS_CHALLENGE3_HARNESS_SELF_TEST_FAIL code={error}", file=sys.stderr)
            return 1

    challenge_value: str | None = None
    try:
        container_id = _target_container_id()
        challenge_value = _challenge_value_from_container(container_id)
        base_url = f"http://127.0.0.1:{_host_port()}"
        status = _exercise(base_url, challenge_value)
        print(f"challenge3_http_status={status}")
        print("challenge3_csrf=present")
        print("Challenge 3 exercise: PASS — value processed in memory and not disclosed")
        return 0
    except SanitisedFailure as error:
        print(f"Challenge 3 exercise: FAIL — code={error}", file=sys.stderr)
        return 1
    except Exception:
        print("Challenge 3 exercise: FAIL — code=unexpected-internal-error", file=sys.stderr)
        return 1
    finally:
        challenge_value = None


if __name__ == "__main__":
    raise SystemExit(main())
