#!/usr/bin/env python3
"""Temporary exact patch for the Runner Protocol repository-local SDK block."""

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one occurrence, found {count}: {old!r}")
    file_path.write_text(text.replace(old, new, 1), encoding="utf-8")


def insert_before(path: str, marker: str, content: str) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    count = text.count(marker)
    if count != 1:
        raise SystemExit(f"{path}: marker expected once, found {count}: {marker!r}")
    file_path.write_text(text.replace(marker, content + marker, 1), encoding="utf-8")


def main() -> None:
    contracts = "platform/runner-protocol/src/runner_protocol_v2/contracts.py"
    replace_once(
        contracts,
        '    candidate = Path(configured).expanduser().resolve() if configured else Path(__file__).resolve().parents[2]\n',
        '    candidate = (\n'
        '        Path(configured).expanduser().resolve()\n'
        '        if configured\n'
        '        else Path(__file__).resolve().parents[2]\n'
        '    )\n',
    )

    conformance = "platform/runner-protocol/conformance.py"
    replace_once(
        conformance,
        'import jsonschema\n\nfrom validate_protocol import request_fingerprint, validate_semantics\n\nROOT = Path(__file__).resolve().parent\n',
        'import jsonschema\n\nROOT = Path(__file__).resolve().parent\nSDK_SRC = ROOT / "src"\nif str(SDK_SRC) not in sys.path:\n    sys.path.insert(0, str(SDK_SRC))\n\nfrom runner_protocol_v2 import request_fingerprint, validate_semantics  # noqa: E402\n\n',
    )

    fixture = "platform/runner-protocol/fixtures/reference_adapter.py"
    replace_once(
        fixture,
        'ROOT = Path(__file__).resolve().parents[1]\nsys.path.insert(0, str(ROOT))\n\nfrom validate_protocol import request_fingerprint, validate_semantics  # noqa: E402\n',
        'ROOT = Path(__file__).resolve().parents[1]\nSDK_SRC = ROOT / "src"\nif str(SDK_SRC) not in sys.path:\n    sys.path.insert(0, str(SDK_SRC))\n\nfrom runner_protocol_v2 import request_fingerprint, validate_semantics  # noqa: E402\n',
    )

    tests = "platform/runner-protocol/tests/test_runner_protocol.py"
    replace_once(
        tests,
        'ROOT = Path(__file__).resolve().parents[1]\nsys.path.insert(0, str(ROOT))\n\nfrom validate_protocol import (  # noqa: E402\n',
        'ROOT = Path(__file__).resolve().parents[1]\nSDK_SRC = ROOT / "src"\nif str(SDK_SRC) not in sys.path:\n    sys.path.insert(0, str(SDK_SRC))\n\nfrom runner_protocol_v2 import (  # noqa: E402\n',
    )

    readme = "platform/runner-protocol/README.md"
    replace_once(
        readme,
        '- Current implementation state: contract and vendor-neutral conformance kit available; no existing API, DevSecOps or AI/MCP runner is claimed conformant.\n',
        '- Current implementation state: contract, repository-local SDK and vendor-neutral conformance kit available; no existing API, DevSecOps or AI/MCP runner is claimed conformant.\n',
    )
    insert_before(
        readme,
        '## Conformance kit\n',
        '''## Repository-local Python SDK

The canonical validation, compatibility, progress and fingerprint logic is exposed through the
`runner_protocol_v2` package under [`src/runner_protocol_v2/`](src/runner_protocol_v2/). The
root [`validate_protocol.py`](validate_protocol.py) file is only a CLI wrapper and contains no
duplicate protocol logic.

For repository development, install the package in editable mode:

```bash
python -m pip install -e platform/runner-protocol
```

Consumers import the explicit package name rather than `platform.*`, avoiding collision with
the Python standard-library `platform` module:

```python
from runner_protocol_v2 import request_fingerprint, validate_semantics
```

The SDK deliberately does not package copied schemas. In an editable repository checkout it
resolves the canonical `schemas/` and `compatibility.yaml` artefacts beside the project. A
non-editable installation must set `RUNNER_PROTOCOL_CONTRACT_ROOT` to that canonical contract
directory. Missing or incomplete contract artefacts fail closed.

The SDK is side-effect free: it does not dispatch, authorize, cancel or execute work. It is a
shared dependency for future adapters so validation and fingerprint semantics are not copied or
reinterpreted per runner family.

''',
    )
    replace_once(
        readme,
        '- [`schemas/runner-protocol-v2.schema.json`](schemas/runner-protocol-v2.schema.json)\n- [`validate_protocol.py`](validate_protocol.py)\n',
        '- [`schemas/runner-protocol-v2.schema.json`](schemas/runner-protocol-v2.schema.json)\n- [`pyproject.toml`](pyproject.toml)\n- [`src/runner_protocol_v2/`](src/runner_protocol_v2/)\n- [`validate_protocol.py`](validate_protocol.py) — thin CLI wrapper\n',
    )
    replace_once(
        readme,
        '- [`tests/test_runner_protocol.py`](tests/test_runner_protocol.py)\n- [`tests/test_conformance.py`](tests/test_conformance.py)\n',
        '- [`tests/test_runner_protocol.py`](tests/test_runner_protocol.py)\n- [`tests/test_conformance.py`](tests/test_conformance.py)\n- [`tests/test_sdk.py`](tests/test_sdk.py)\n',
    )

    epic = "docs/roadmap/epics/EPIC-05-runner-protocol-v2.md"
    replace_once(epic, "| Document version | 1.3.0 |", "| Document version | 1.3.1 |")
    replace_once(
        epic,
        "demonstrated end-to-end conformance, idempotent effects or bounded live cancellation.\n",
        "demonstrated end-to-end conformance, idempotent effects or bounded live cancellation.\n"
        "A repository-local importable SDK is being extracted as block 3 before any real adapter\n"
        "is implemented, preventing adapter-specific copies of canonical validation logic.\n",
    )
    insert_before(
        epic,
        "## 15. As-built / final architecture\n",
        '''### Block 3 — repository-local importable SDK (`IMPLEMENTING`)

- Branch: `refactor/epic-05-runner-protocol-sdk`
- Package: `runner_protocol_v2`
- Source: `platform/runner-protocol/src/runner_protocol_v2/`
- Canonical schemas: retained once under `platform/runner-protocol/schemas/`
- CLI: thin wrapper over the SDK
- Contract resolution: editable repository root or explicit `RUNNER_PROTOCOL_CONTRACT_ROOT`
- Missing contract artefacts: fail closed
- Existing API, DevSecOps and AI/MCP adapters: `NOT_RUN`
- Runtime declaration: `NO_RUNTIME_CHANGE`

This block is a prerequisite for adapters. It must demonstrate direct package import, canonical
contract resolution, rejection of an incomplete explicit contract root and absence of duplicate
validation implementations before merge.

''',
    )
    replace_once(
        epic,
        "| 2026-08-06 | 1.3.0 | Record conformance kit AS_BUILT, merge/CI evidence, controlled rejection proofs and residual limitations. |",
        "| 2026-08-06 | 1.3.0 | Record conformance kit AS_BUILT, merge/CI evidence, controlled rejection proofs and residual limitations. |\n"
        "| 2026-08-06 | 1.3.1 | Start block 3 repository-local SDK extraction before implementing real adapters. |",
    )

    for temporary in (
        ".github/workflows/epic-05-sdk-patch-once.yml",
        "tools/tmp_epic05_sdk_patch.py",
    ):
        path = Path(temporary)
        if path.exists():
            path.unlink()


if __name__ == "__main__":
    main()
