.PHONY: help validate lint test compose fmt

help:
	@echo "make validate   catalog + maturity audit + security catalog + shell syntax"
	@echo "make test       per-directory pytest suites (the CI contract)"
	@echo "make lint       ruff over the exact paths CI lints"
	@echo "make compose    compose config --quiet for the reference labs"
	@echo "make fmt        prettier (best effort, optional)"
	@echo "Short operating path: docs/quickstart.md"

validate:
	python3 platform/scripts/labctl.py validate
	python3 platform/scripts/lab_audit.py audit --strict
	python3 platform/scripts/lab_audit.py baseline-check
	python3 security/tools/securityctl.py validate
	git ls-files '*.sh' | xargs -r -n1 bash -n

test:
	python3 -m pytest -q docs/tests -p no:cacheprovider
	python3 -m pytest -q deployment/tests -p no:cacheprovider
	python3 -m pytest -q roadmap/tests -p no:cacheprovider
	python3 -m pytest -q platform/tests -p no:cacheprovider

# Reproduces the CI gate exactly. A bare `ruff check .` is NOT the gate: it reports
# pre-existing findings in paths CI does not lint.
lint:
	RUFF_CACHE_DIR=$${TMPDIR:-/tmp}/ruff-cache python3 -m ruff check --config security/pyproject.toml \
	  security/core/src security/core/tests \
	  security/packs/api/src security/packs/api/tests \
	  security/packs/devsecops/tools security/packs/devsecops/tests \
	  security/packs/ai-mcp/tools security/packs/ai-mcp/tests \
	  security/tools security/tests \
	  docs/tests deployment \
	  platform/scripts/validate_source_of_truth.py \
	  platform/tests platform/runner-protocol

compose:
	docker compose -p hermes-kali-mcp -f kali-mcp/compose.yaml config --quiet
	docker compose -p juice-shop -f platform/environments/web-api/juice-shop/compose.yaml config --quiet

fmt:
	prettier --write '**/*.{yaml,yml,md,json}' || true
