from __future__ import annotations

from pathlib import Path

SELF = Path(__file__)
WORKFLOW = Path(".github/workflows/epic-05-supervised-adapter-readiness-once.yml")
TARGET = Path(
    "security/packs/api/src/api_pentest_runbooks/supervised_runner_protocol_adapter.py"
)


def replace_once(old: str, new: str) -> None:
    text = TARGET.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected one match, found {count}: {old[:100]!r}")
    TARGET.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once("import threading\n", "import threading\nimport time\n")
replace_once(
    "    spec: SupervisedProcessSpec\n    cancellation: threading.Event = field(default_factory=threading.Event)\n",
    "    spec: SupervisedProcessSpec\n    cleanup_paths: tuple[Path, ...] = ()\n    ready_file: Path | None = None\n    cancellation: threading.Event = field(default_factory=threading.Event)\n",
)
replace_once(
    "    ) -> tuple[SupervisedProcessSpec, Path | None]:\n        assert self.working_directory is not None\n        mode = self._worker_mode(capability)\n        argv = [str(Path(sys.executable).resolve()), str(WORKER), \"--mode\", mode]\n        residue_file: Path | None = None\n        if capability == \"conformance.process.residue\":\n            residue_file = self._residue_pid_file(request[\"idempotency_key\"])\n            residue_file.unlink(missing_ok=True)\n            argv.extend([\"--pid-file\", str(residue_file)])\n",
    "    ) -> tuple[SupervisedProcessSpec, tuple[Path, ...], Path | None]:\n        assert self.working_directory is not None\n        mode = self._worker_mode(capability)\n        argv = [str(Path(sys.executable).resolve()), str(WORKER), \"--mode\", mode]\n        cleanup_paths: list[Path] = []\n        ready_file: Path | None = None\n        if capability == \"conformance.process.residue\":\n            residue_file = self._residue_pid_file(request[\"idempotency_key\"])\n            residue_file.unlink(missing_ok=True)\n            cleanup_paths.append(residue_file)\n            argv.extend([\"--pid-file\", str(residue_file)])\n        if capability in {\n            \"conformance.process.timeout\",\n            \"conformance.process.cancel\",\n        }:\n            digest = hashlib.sha256(\n                request[\"idempotency_key\"].encode(\"utf-8\")\n            ).hexdigest()[:20]\n            ready_file = self.working_directory / f\".supervised-ready-{digest}.pid\"\n            ready_file.unlink(missing_ok=True)\n            cleanup_paths.append(ready_file)\n            argv.extend([\"--ready-file\", str(ready_file)])\n",
)
replace_once(
    "        return spec, residue_file\n",
    "        return spec, tuple(cleanup_paths), ready_file\n",
)
replace_once(
    "        cancellation: threading.Event | None = None,\n        residue_file: Path | None = None,\n",
    "        cancellation: threading.Event | None = None,\n        cleanup_paths: tuple[Path, ...] = (),\n",
)
replace_once(
    "        finally:\n            if residue_file is not None:\n                residue_file.unlink(missing_ok=True)\n",
    "        finally:\n            for cleanup_path in cleanup_paths:\n                cleanup_path.unlink(missing_ok=True)\n",
)
replace_once(
    "            pending.spec,\n            cancellation=pending.cancellation,\n        )\n",
    "            pending.spec,\n            cancellation=pending.cancellation,\n            cleanup_paths=pending.cleanup_paths,\n        )\n",
)
replace_once(
    "            spec, residue_file = self._spec(request, capability)\n",
    "            spec, cleanup_paths, ready_file = self._spec(request, capability)\n",
)
replace_once(
    "        if preflight is not None:\n            if residue_file is not None:\n                residue_file.unlink(missing_ok=True)\n            return preflight\n",
    "        if preflight is not None:\n            for cleanup_path in cleanup_paths:\n                cleanup_path.unlink(missing_ok=True)\n            return preflight\n",
)
replace_once(
    "                spec,\n                residue_file=residue_file,\n            )\n",
    "                spec,\n                cleanup_paths=cleanup_paths,\n            )\n",
)
replace_once(
    "            fingerprint=fingerprint,\n            spec=spec,\n        )\n",
    "            fingerprint=fingerprint,\n            spec=spec,\n            cleanup_paths=cleanup_paths,\n            ready_file=ready_file,\n        )\n",
)
replace_once(
    "        try:\n            thread.start()\n        except RuntimeError:\n",
    "        try:\n            thread.start()\n        except RuntimeError:\n",
)
replace_once(
    "            return self._complete_response(\n                key=key,\n                fingerprint=fingerprint,\n                correlation=request[\"correlation\"],\n                response=response,\n            )\n        return {\"messages\": [_progress(request[\"correlation\"])]}\n",
    "            return self._complete_response(\n                key=key,\n                fingerprint=fingerprint,\n                correlation=request[\"correlation\"],\n                response=response,\n            )\n\n        if ready_file is not None:\n            deadline = time.monotonic() + 2\n            while (\n                not ready_file.is_file()\n                and not pending.done.is_set()\n                and time.monotonic() < deadline\n            ):\n                time.sleep(0.01)\n            if pending.done.is_set():\n                with self._process_lock:\n                    self.process_pending.pop(key, None)\n                return pending.response or {\n                    \"transport_error\": \"synthetic process ended without a response\"\n                }\n            if not ready_file.is_file():\n                pending.cancellation.set()\n                pending.done.wait(\n                    (spec.termination_grace_ms + spec.cleanup_timeout_ms + 1_000)\n                    / 1_000\n                )\n                with self._process_lock:\n                    self.process_pending.pop(key, None)\n                return pending.response or {\n                    \"transport_error\": \"synthetic process readiness failed closed\"\n                }\n        return {\"messages\": [_progress(request[\"correlation\"])]}\n",
)

SELF.unlink()
WORKFLOW.unlink()
