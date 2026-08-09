# Changelog

## 2026-08-09

- Wave 1 Lane E2 (repo-first runtime remediation): entrega dos remanescentes
  do lane sem mutação de host/container/rede ou GHCR.
- `kali-mcp/tool_health.py`: classificador determinístico PRESENT/READY/DEGRADED
  para ferramentas Kali (reproduz a deriva WPScan observada).
- `kali-mcp/config/mcp-connectivity.example.yaml`: perfil canónico de
  conectividade host→Kali MCP, loopback-only / STDIO-docker-exec, nunca 0.0.0.0;
  exemplo de registro (não escrito em `~/.hermes`).
- `platform/tests/test_kali_tool_health_states.py`,
  `platform/tests/test_kali_mcp_connectivity_profile.py`: validadores.
- `docs/kali-mcp-live-drift-and-migration.md`: documenta deriva entre runtime
  vivo e canónico + runbook determinístico sem eliminação automática.
- Nuclei permanece diferido (sem cenário/runbook ativo que o mapeie).

## 2026-08-06

- EPIC-01 iniciou a implementação da arquitetura canónica da Security Validation Platform v2.
- TB0–TB4 passaram a identificar travessias entre domínios de confiança, com responsabilidades, proibições, contratos e falha segura explícitos.
- Foi criado o registo inicial de Architecture Decision Records e o inventário canónico de contratos cross-plane.
- Foram adicionados gates documentais para numeração, cobertura e integridade dos ADRs e contratos.
- Sem alteração de runtime, laboratórios, containers, redes ou deployment.

## 2026-07-30
- baseline auditada
- Kali MCP 0.2.0 validada
- Juice Shop laboratorial adicionado
