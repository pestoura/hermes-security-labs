.PHONY: validate compose scripts fmt

validate:
	bash -n kali-mcp/scripts/*.sh platform/scripts/*.sh || true

compose:
	docker compose -p hermes-kali-mcp -f kali-mcp/compose.yaml config --quiet
	docker compose -p juice-shop -f platform/environments/web-api/juice-shop/compose.yaml config --quiet

fmt:
	prettier --write '**/*.{yaml,yml,md,json}' || true
