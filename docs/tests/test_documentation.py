"""Lightweight documentation integrity tests.

Pure standard library. No network, no external binaries, no global installs.

Covers:
- canonical documents exist;
- the main README references the canonical navigation;
- the navigation references every canonical document;
- Mermaid fences are closed and use GitHub-supported diagram types;
- relative Markdown links resolve inside the repository;
- documented commands that reference repository paths point to existing paths.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"

CANONICAL_DOCS = (
    "project-overview.md",
    "repository-tour.md",
    "architecture.md",
    "quickstart.md",
    "getting-started.md",
    "operator-guide.md",
    "contributor-guide.md",
    "troubleshooting.md",
    "security-model.md",
    "glossary-and-references.md",
    "documentation-governance.md",
)

# Diagram types GitHub renders natively.
SUPPORTED_MERMAID_TYPES = {
    "flowchart",
    "graph",
    "sequencediagram",
    "statediagram",
    "statediagram-v2",
    "classdiagram",
    "erdiagram",
    "journey",
    "gantt",
    "pie",
    "mindmap",
    "timeline",
    "gitgraph",
    "quadrantchart",
    "requirementdiagram",
    "c4context",
    "xychart-beta",
    "block-beta",
    "sankey-beta",
}

LINK_RE = re.compile(r"(?<!\!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
FENCE_RE = re.compile(r"^```(\w[\w-]*)?\s*$")


def _markdown_files() -> list[Path]:
    skip_parts = {".git", "node_modules", "__pycache__", ".runtime", ".venv"}
    files = []
    for path in ROOT.rglob("*.md"):
        if skip_parts & set(path.parts):
            continue
        files.append(path)
    return sorted(files)


def _code_blocks(text: str) -> list[tuple[str, str]]:
    """Return (language, body) for every fenced block."""
    blocks: list[tuple[str, str]] = []
    lang: str | None = None
    buf: list[str] = []
    for line in text.splitlines():
        match = FENCE_RE.match(line)
        if match and lang is None:
            lang = (match.group(1) or "").lower()
            buf = []
            continue
        if line.strip() == "```" and lang is not None:
            blocks.append((lang, "\n".join(buf)))
            lang = None
            buf = []
            continue
        if lang is not None:
            buf.append(line)
    return blocks


def test_canonical_documents_exist() -> None:
    missing = [name for name in CANONICAL_DOCS if not (DOCS / name).is_file()]
    assert not missing, f"missing canonical documents: {missing}"


def test_documentation_index_exists() -> None:
    assert (DOCS / "README.md").is_file(), "docs/README.md navigation is missing"


def test_main_readme_links_documentation_index() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/README.md" in readme, (
        "README.md must link the canonical documentation index docs/README.md"
    )


def test_index_references_every_canonical_document() -> None:
    index = (DOCS / "README.md").read_text(encoding="utf-8")
    missing = [name for name in CANONICAL_DOCS if name not in index]
    assert not missing, f"docs/README.md does not reference: {missing}"


@pytest.mark.parametrize("path", _markdown_files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_code_fences_are_balanced(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert text.count("```") % 2 == 0, f"unbalanced code fences in {path.relative_to(ROOT)}"


@pytest.mark.parametrize("path", _markdown_files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_mermaid_blocks_are_supported(path: Path) -> None:
    for lang, body in _code_blocks(path.read_text(encoding="utf-8")):
        if lang != "mermaid":
            continue
        stripped = [ln for ln in body.splitlines() if ln.strip() and not ln.strip().startswith("%%")]
        assert stripped, f"empty mermaid block in {path.relative_to(ROOT)}"
        first = stripped[0].strip().split()[0].lower().rstrip(":")
        assert first in SUPPORTED_MERMAID_TYPES, (
            f"unsupported mermaid diagram type {first!r} in {path.relative_to(ROOT)}"
        )


def test_architecture_document_has_required_diagrams() -> None:
    text = (DOCS / "architecture.md").read_text(encoding="utf-8")
    kinds = {
        lang_body[1].strip().splitlines()[0].strip().split()[0].lower()
        for lang_body in _code_blocks(text)
        if lang_body[0] == "mermaid"
    }
    for required in ("flowchart", "sequencediagram", "statediagram-v2"):
        assert required in kinds, f"docs/architecture.md is missing a {required} diagram"


@pytest.mark.parametrize("path", _markdown_files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_relative_links_resolve(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    # Ignore link-like text inside fenced code blocks.
    for _lang, body in _code_blocks(text):
        text = text.replace(body, "")

    broken: list[str] = []
    for target in LINK_RE.findall(text):
        if target.startswith(("http://", "https://", "mailto:", "#", "<")):
            continue
        clean = target.split("#", 1)[0]
        if not clean:
            continue
        resolved = (path.parent / clean).resolve()
        if not resolved.exists():
            broken.append(target)
    assert not broken, f"broken relative links in {path.relative_to(ROOT)}: {broken}"


@pytest.mark.parametrize(
    "doc",
    [
        "quickstart.md",
        "getting-started.md",
        "operator-guide.md",
        "contributor-guide.md",
        "troubleshooting.md",
    ],
)
def test_documented_repository_paths_exist(doc: str) -> None:
    """Command examples must not reference repository paths that do not exist."""
    text = (DOCS / doc).read_text(encoding="utf-8")
    prefixes = (
        "security/",
        "platform/",
        "deployment/",
        "roadmap/",
        "schemas/",
        "kali-mcp/",
        "docs/",
    )
    token_re = re.compile(r"[A-Za-z0-9_./-]+")
    missing: list[str] = []

    for lang, body in _code_blocks(text):
        if lang not in ("bash", "sh", "shell", ""):
            continue
        for token in token_re.findall(body):
            if not token.startswith(prefixes):
                continue
            if any(ch in token for ch in "*<>"):
                continue
            if token.endswith((".py", ".sh", ".yaml", ".yml", ".json", ".md")):
                if not (ROOT / token).exists():
                    missing.append(token)
            elif token.endswith("/") or "/" in token:
                if not (ROOT / token.rstrip("/")).exists():
                    missing.append(token)

    assert not missing, f"docs/{doc} references non-existent repository paths: {sorted(set(missing))}"
