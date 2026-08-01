# Phase 2 environment batch

This batch implements repository-side candidates for the remaining Phase 2 environments. WrongSecrets remains in PR #58.

| Environment | Upstream/source | Immutable revision | Port | Profile |
|---|---|---|---:|---|
| `cicd-goat` | `cider-security-research/cicd-goat` | `0ed10925f3983857cf219b2ac1c327b861fcccca` | 8201 | `cicd` / CURRENT-LIMITED |
| `damn-vulnerable-sca` | `harekrishnarai/Damn-vulnerable-sca` | `fa5d063a5588c404dc3a222bd3f10965666c01db` | 8202 | `sca` / CURRENT-LIMITED |
| `terragoat` | `bridgecrewio/terragoat` | `729f8da62c6a85ce4af5ad3d123de97776d954c4` | 8203 | `iac` / CURRENT-LIMITED |
| `cdkgoat` | `bridgecrewio/cdkgoat` | `c6c0278a49083526c462c80d6ff95e32db83f6a8` | 8204 | `iac` / CURRENT-LIMITED |
| `cfngoat` | `bridgecrewio/cfngoat` | `0c09b69cfc3dbc6cb3ef01883415c35c588ced48` | 8205 | `iac` / CURRENT-LIMITED |
| `bicepgoat` | `bridgecrewio/bicepgoat` | `83388f40be34af3146eb484d635e413383b28d16` | 8206 | `iac` / CURRENT-LIMITED |
| `promptme` | `R3dShad0w7/PromptMe` | `fd7676c323698e824f4417bd5d116c18baabe902` | 8210 | `prompt` / CURRENT-LIMITED |
| `vulnerable-mcp-servers` | `pfelilpe/DVMCP` | `75dc4ec58423be3aea11476eda17085bf7498e81` | 8211 | `mcp` / CURRENT-LIMITED |
| `llmforge` | `SasanLabs/LLMForge` | `62c756fc79343e4fbf2344eaf683e9a44e6ca5c3` | 8212 | `llm` / CURRENT-LIMITED |
| `damn-vulnerable-llm-agent` | `ReversecLabs/damn-vulnerable-llm-agent` | `c0cf9a14adad76e9d6a53c41741f625334bd9971` | 8213 | `agent` / CURRENT-LIMITED |
| `prompt-injection-lab` | `pestoura/hermes-security-labs` | `synthetic-v1` | 8214 | `prompt` / CURRENT-LIMITED |
| `tool-poisoning-lab` | `pestoura/hermes-security-labs` | `synthetic-v1` | 8215 | `tool` / CURRENT-LIMITED |
| `rag-poisoning-lab` | `pestoura/hermes-security-labs` | `synthetic-v1` | 8216 | `rag` / CURRENT-LIMITED |

## Local validation

Static only:

```bash
platform/scripts/phase2-local-validation.sh
```

Sequential runtime campaign:

```bash
PHASE2_RUN_RUNTIME=1 platform/scripts/phase2-local-validation.sh
```

The runtime campaign intentionally processes one environment at a time.
