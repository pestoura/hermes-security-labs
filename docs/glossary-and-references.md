# Glossary and references

## Termos do projeto

| Termo | Definição |
| --- | --- |
| **Laboratório (lab)** | ambiente vulnerável descartável definido por manifesto em `platform/environments/` |
| **Runbook** | definição determinística de um teste, em YAML, num pack de domínio |
| **Campanha** | conjunto ordenado de runbooks executado contra um laboratório |
| **Binding** | ligação canónica pack ↔ campanha ↔ laboratório em `security/bindings/labs.yaml` |
| **Adapter** | tradutor de runbook em pedido tipado para o runner |
| **Runner** | componente que executa a operação e devolve saída normalizada |
| **Capability** | operação disponível no execution plane; hoje as 12 ferramentas do Kali MCP |
| **Control plane** | Hermes: autorização, planeamento, avaliação, estado |
| **Execution plane** | Kali MCP e runners |
| **Target plane** | laboratórios e runtimes isolados |
| **Evidence plane** | armazenamento append-only de evidência, fora do Git |
| **Pack** | unidade de domínio em `security/packs/<domain>` |
| **Manifesto** | YAML que descreve origem, versão, recursos, runtime, egress e lifecycle de um laboratório |
| **Attach / detach** | ligar e desligar o Kali da rede do laboratório ativo |
| **Readiness** | o serviço responde ao contrato esperado (distinto de health) |
| **Health** | o processo está vivo segundo o Docker |
| **Drift** | divergência entre estado aplicado e commit registado |
| **`IN_SYNC` / `DRIFT_DETECTED` / `UNKNOWN`** | tri-estado de deployment; nunca falha aberto |
| **Calibração** | validação de um runbook com controlo positivo e negativo |
| **Sanitização** | remoção de segredos e dados não partilháveis da evidência |
| **Quarentena** | recurso residual que não pôde ser removido com prova |
| **SVP2** | Security Validation Platform v2, o roadmap |
| **Pilar** | agrupamento A–L do backlog v2 |

## Frameworks e fontes

Distinção obrigatória: **atual** significa que existe uso ou mapeamento no
repositório hoje; **planeada** significa roadmap.

| Sigla | Nome | Uso | Estado |
| --- | --- | --- | --- |
| **PTES** | Penetration Testing Execution Standard | estrutura de fases de campanha | atual (referência) |
| **NIST** | NIST SP 800-115 / CSF | enquadramento metodológico e de controlo | atual (referência) |
| **OWASP** | Open Worldwide Application Security Project (Top 10, ASVS, API Top 10, WSTG) | classificação de runbooks Web/API | atual |
| **ATT&CK** | MITRE ATT&CK | mapeamento de técnicas adversárias | planeada (`SVP2-F-01`) |
| **ATLAS** | MITRE ATLAS | técnicas adversárias contra sistemas de IA/ML | planeada (`SVP2-F-01`) |
| **CWE** | Common Weakness Enumeration | classificação de fraquezas | planeada (crosswalk) |
| **CAPEC** | Common Attack Pattern Enumeration and Classification | padrões de ataque | planeada (crosswalk) |
| **CVE / NVD** | Common Vulnerabilities and Exposures / National Vulnerability Database | identificação de vulnerabilidades conhecidas | planeada (`SVP2-E-01`) |
| **KEV** | CISA Known Exploited Vulnerabilities | priorização por exploração observada | planeada (`SVP2-G-01`) |
| **EPSS** | Exploit Prediction Scoring System | probabilidade de exploração | planeada (`SVP2-J-01`) |
| **OSCAL** | Open Security Controls Assessment Language | interoperabilidade de controlos e resultados | planeada (`SVP2-J-02`) |
| **CACAO** | Collaborative Automated Course of Action Operations | playbooks de resposta automatizável | planeada (`SVP2-J-02`) |
| **Attack Flow** | MITRE Attack Flow | encadeamento de técnicas | planeada (`SVP2-J-02`) |
| **SBOM / SLSA** | Software Bill of Materials / Supply-chain Levels for Software Artifacts | proveniência e promoção de imagens | parcial: GHCR com metadados OCI é atual; assinatura e SLSA são planeadas (`SVP2-C-02`) |
| **OCI** | Open Container Initiative | metadados e digests de imagem | atual |
| **GHCR** | GitHub Container Registry | registo de imagens do projeto | atual |
| **MCP** | Model Context Protocol | transporte entre Hermes e o Kali | atual |

Detalhe de mapeamento e níveis de confiança em
[framework crosswalk](architecture/framework-crosswalk.md) e
[security knowledge fabric](architecture/security-knowledge-fabric.md).

## Ver também

- [Project overview](project-overview.md)
- [Security model](security-model.md)
