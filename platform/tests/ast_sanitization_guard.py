"""AST sanitization guard for the PTaaS vertical-slice binder (CHG-HSL-084 Task 15).

Proves the no-authority / no-effect property of
``platform/slice-contract/slice_binder.py`` by real AST analysis instead of a
substring scan:

* import detection resolves dotted modules, aliases (``import subprocess as sp``)
  and ``from X import y`` bindings, matching a forbidden module or any submodule
  of it;
* call detection only flags an effect-bearing attribute (``run``, ``Popen``,
  ``sendall``, ``system``, ...) when the call's BASE resolves to a name bound to a
  forbidden module. Attributes on unrelated objects (``json.dumps``,
  ``chain.append_object``) are never flagged.

Consequence: docstrings and path STRINGS that legitimately name the forbidden
modules (the binder documents them, and references the adapter as a path string)
produce no false positives, because only real ``Import``/``ImportFrom``/``Call``
nodes are inspected.

This module holds no authority and performs no effect: pure ``ast`` inspection,
no import of the analysed source, no filesystem write, no network, no subprocess,
no Vault/secret access.
"""

from __future__ import annotations

import ast
from typing import Any, Dict, Iterable, List

#: Authority/effect modules the binder must never import or call into.
#: Plan-listed (Task 15 / Task 10 no-import rule): runner_protocol_v2, subprocess,
#: socket plus the network/authority/effect surfaces named by the slice plan.
FORBIDDEN_MODULES: frozenset[str] = frozenset(
    {
        "runner_protocol_v2",
        "subprocess",
        "socket",
        "requests",
        "http",
        "urllib",
        "ftplib",
        "telnetlib",
        "asyncio",
        "multiprocessing",
        "runner_handoff",
        "admission",
        "router",
        "webgoat_l1_adapter",
        "hvac",
    }
)

#: Effect-bearing attribute names, only reported on a forbidden base.
EFFECT_ATTRS: frozenset[str] = frozenset(
    {
        "run",
        "Popen",
        "call",
        "check_call",
        "check_output",
        "system",
        "popen",
        "exec",
        "execv",
        "execve",
        "spawn",
        "spawnv",
        "fork",
        "send",
        "sendall",
        "sendto",
        "connect",
        "connect_ex",
        "bind",
        "listen",
        "accept",
        "urlopen",
        "request",
    }
)


def _root(dotted: str) -> str:
    return dotted.split(".", 1)[0]


def _is_forbidden(dotted: str) -> bool:
    return _root(dotted) in FORBIDDEN_MODULES


def forbidden_imports(tree: ast.AST) -> List[Dict[str, Any]]:
    """Return one finding per real import of a forbidden module."""
    found: List[Dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_forbidden(alias.name):
                    found.append(
                        {
                            "kind": "import",
                            "module": _root(alias.name),
                            "binding": alias.asname or _root(alias.name),
                            "lineno": node.lineno,
                        }
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module and _is_forbidden(module):
                for alias in node.names:
                    found.append(
                        {
                            "kind": "import_from",
                            "module": _root(module),
                            "binding": alias.asname or alias.name,
                            "lineno": node.lineno,
                        }
                    )
    return found


def forbidden_bindings(tree: ast.AST) -> Dict[str, str]:
    """Map local names bound to forbidden modules -> forbidden module root."""
    bindings: Dict[str, str] = {}
    for finding in forbidden_imports(tree):
        bindings[finding["binding"]] = finding["module"]
    return bindings


def _base_name(node: ast.AST) -> str | None:
    """Resolve the leftmost Name of an attribute/call chain, if any."""
    cur: ast.AST = node
    while True:
        if isinstance(cur, ast.Name):
            return cur.id
        if isinstance(cur, ast.Attribute):
            cur = cur.value
            continue
        if isinstance(cur, ast.Call):
            cur = cur.func
            continue
        return None


def forbidden_calls(tree: ast.AST) -> List[Dict[str, Any]]:
    """Return one finding per call of an effect attribute on a forbidden base."""
    bindings = forbidden_bindings(tree)
    if not bindings:
        return []
    found: List[Dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            attr = func.attr
            base = _base_name(func.value)
        elif isinstance(func, ast.Name):
            attr = func.id
            base = func.id
        else:
            continue
        if base is None or base not in bindings:
            continue
        if attr in EFFECT_ATTRS or attr in bindings:
            found.append(
                {
                    "kind": "call",
                    "module": bindings[base],
                    "base": base,
                    "attr": attr,
                    "lineno": node.lineno,
                }
            )
    return found


def analyze_source(source: str) -> Dict[str, List[Dict[str, Any]]]:
    """Convenience wrapper: parse ``source`` and return both finding lists."""
    tree = ast.parse(source)
    return {"imports": forbidden_imports(tree), "calls": forbidden_calls(tree)}


def iter_findings(source: str) -> Iterable[Dict[str, Any]]:
    result = analyze_source(source)
    return [*result["imports"], *result["calls"]]
