> **Localização canónica:** `security/packs/devsecops` no monorepo `pestoura/hermes-security-labs`.  
> Importado de `pestoura/devsecops-security-runbooks@3588270e9e56f73fe7b7aff46944a1b87d5fde27`; o repositório autónomo é apenas histórico de migração.

# DevSecOps Security Runbooks

Biblioteca versionada de **120 runbooks machine-readable** para o domínio `devsecops`.

Cada runbook é um ficheiro YAML individual em `runbooks/`. Os YAML são a fonte canónica; CSV e relatórios são derivados.

## Cobertura

- `repository`: 12
- `secrets`: 16
- `sca`: 16
- `sbom`: 12
- `oci`: 14
- `cicd`: 16
- `supplychain`: 12
- `iac`: 16
- `evidence`: 6

## Definição materializada

Cada runbook tem ID único, seletores de target, capacidades, limites de risco, três passos tipados, critérios específicos de avaliação, requisitos determinísticos de evidência e finding de saída. Nenhum runbook contém campos livres `shell`, `script`, `command` ou `argv`.

## Estado de validação

As definições estão estruturalmente completas e validadas em CI. Permanecem `experimental` até os controlos positivos e negativos serem calibrados nos laboratórios autorizados. Completude estrutural não prova deteção operacional num target real.

## Comandos no monorepo

```bash
cd security/packs/devsecops
python tools/validate_pack.py
pytest -q
python tools/export_catalog.py --output dist/catalog.csv
```

A ligação aos laboratórios é canónica em `../../bindings/labs.yaml`.
