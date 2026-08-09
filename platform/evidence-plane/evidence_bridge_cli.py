#!/usr/bin/env python3
"""CLI helper for the execution-scoped evidence bridge.

Subcommands (all local, read-only except explicit emit/project writes):

    emit     --spec <file.json> --results-root <dir>
    verify   --results-root <dir> --execution-id <id>
    show     --results-root <dir> --execution-id <id>
    project  --results-root <dir> --execution-id <id> --store <dir> [--include-payloads]
    self-test

The CLI performs no offensive execution, no network access and no target interaction.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name: str, filename: str):
    module_name = f"_evidence_bridge_cli_{name}"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, HERE / filename)
    if not spec or not spec.loader:
        raise RuntimeError(f"cannot load module: {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


bridge = _load("bridge", "execution_bridge.py")
store_module = _load("store", "local_store.py")


def _print(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True))


def _cmd_emit(args: argparse.Namespace) -> int:
    spec = json.loads(Path(args.spec).expanduser().read_bytes())
    manifest = bridge.emit_from_spec(spec, args.results_root)
    _print(
        {
            "execution_id": manifest["execution_id"],
            "result_digest": manifest["result_digest"],
            "manifest_path": str(
                (Path(args.results_root).expanduser() / manifest["execution_id"] / "manifest.json").resolve()
            ),
        }
    )
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    report = bridge.verify_execution(args.results_root, args.execution_id)
    _print(report)
    return 0 if report["verified"] else 1


def _cmd_show(args: argparse.Namespace) -> int:
    manifest = bridge.load_manifest(args.results_root, args.execution_id)
    _print(bridge.summarize_manifest(manifest))
    return 0


def _cmd_project(args: argparse.Namespace) -> int:
    store = store_module.LocalEvidenceStore(args.store)
    result = bridge.project_execution(
        store,
        args.results_root,
        args.execution_id,
        include_payloads=args.include_payloads,
    )
    _print(result)
    return 0


SELF_TEST_SPEC = {
    "execution_id": "exec-self-test-0001",
    "environment": "reference-fixture-lab",
    "scenario": "reference-scenario",
    "target": "reference-target",
    "tool": "reference-tool",
    "correlation": {
        "campaign_id": "campaign-self-test",
        "run_id": "run-self-test",
        "step_id": "step-1",
        "attempt_id": "attempt-1",
    },
    "started_at": "2026-01-01T00:00:00Z",
    "ended_at": "2026-01-01T00:00:05Z",
    "status": "completed",
    "result": "inconclusive",
    "metadata": {"lab_profile": "reference", "sanitized": True},
    "findings": {"schema_version": "1.0", "findings": []},
    "outputs": [
        {"section": "logs", "name": "runner.log", "role": "log", "media_type": "text/plain", "text": "ok\n"},
        {
            "section": "evidence",
            "name": "raw-output.txt",
            "role": "raw_output",
            "media_type": "text/plain",
            "text": "reference output\n",
        },
    ],
}


def _cmd_self_test(_: argparse.Namespace) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "results"
        manifest = bridge.emit_from_spec(SELF_TEST_SPEC, root)
        report = bridge.verify_execution(root, manifest["execution_id"])
        if not report["verified"]:
            _print({"self_test": "FAIL", "report": report})
            return 1
        second = bridge.emit_from_spec(SELF_TEST_SPEC, Path(tmp) / "results-2")
        if second["result_digest"] != manifest["result_digest"]:
            _print({"self_test": "FAIL", "reason": "non-deterministic result digest"})
            return 1
        store = store_module.LocalEvidenceStore(Path(tmp) / "store")
        projection = bridge.project_execution(store, root, manifest["execution_id"])
        if not store.verify(projection["summary_evidence_id"]):
            _print({"self_test": "FAIL", "reason": "summary projection failed verification"})
            return 1
        _print(
            {
                "self_test": "OK",
                "execution_id": manifest["execution_id"],
                "result_digest": manifest["result_digest"],
                "references_checked": report["references_checked"],
                "summary_evidence_id": projection["summary_evidence_id"],
            }
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Execution-scoped evidence bridge helper")
    sub = parser.add_subparsers(dest="command", required=True)

    emit = sub.add_parser("emit", help="emit an execution from a declarative spec")
    emit.add_argument("--spec", required=True)
    emit.add_argument("--results-root", required=True)
    emit.set_defaults(func=_cmd_emit)

    verify = sub.add_parser("verify", help="verify manifest and referenced payload digests")
    verify.add_argument("--results-root", required=True)
    verify.add_argument("--execution-id", required=True)
    verify.set_defaults(func=_cmd_verify)

    show = sub.add_parser("show", help="print the bounded digest-only execution summary")
    show.add_argument("--results-root", required=True)
    show.add_argument("--execution-id", required=True)
    show.set_defaults(func=_cmd_show)

    project = sub.add_parser("project", help="project an execution onto Evidence Plane v2")
    project.add_argument("--results-root", required=True)
    project.add_argument("--execution-id", required=True)
    project.add_argument("--store", required=True)
    project.add_argument("--include-payloads", action="store_true")
    project.set_defaults(func=_cmd_project)

    self_test = sub.add_parser("self-test", help="run the deterministic local self-test")
    self_test.set_defaults(func=_cmd_self_test)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (bridge.ExecutionEvidenceError, store_module.LocalEvidenceStoreError, OSError, ValueError) as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
