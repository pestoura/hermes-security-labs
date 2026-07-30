# Hermes Security Labs

Plataforma segregada de laboratórios de cibersegurança para o Hermes, com Kali MCP, ambientes vulneráveis multi-runtime, automação de lifecycle e verificação de deployment.

## Modelo operacional

- **GitHub:** fonte de verdade de código, configuração, manifestos, documentação e workflows.
- **Hermes:** host e orquestrador dos laboratórios locais.
- **Docker:** runtime principal para Web/API, DevSecOps, IA/MCP e serviços sintéticos.
- **Kubernetes:** clusters descartáveis com kind/k3d.
- **VM/cloud/emulator:** runtimes preparados por manifesto e ativados apenas quando existirem recursos e autorização.
- **Kali MCP:** mantém as 12 ferramentas; a segregação é aplicada por rede, target, egress e lifecycle.

O repositório não contém segredos, resultados brutos, imagens runtime, credenciais, tokens ou dados pessoais.

## Estrutura

```text
kali-mcp/                 imagem e Compose do Kali MCP
platform/environments/    manifestos e implementações dos laboratórios
platform/registry.yaml    runtimes, estados e descoberta do catálogo
platform/rollout.yaml     instalação faseada dos ambientes
platform/scripts/         CLI e wrappers de catálogo/lifecycle
platform/schemas/         schema dos manifestos
deployment/               deploy, verify, rollback e drift detection
skills/                   instruções do agente Hermes
```

## Catálogo

A descoberta suporta temporariamente dois layouts:

```text
platform/environments/<category>/<id>.yaml
platform/environments/<category>/<id>/manifest.yaml
```

Comandos read-only:

```bash
./platform/scripts/lab-list.sh
./platform/scripts/lab-list.sh --runtime docker
./platform/scripts/lab-status.sh juice-shop
./platform/scripts/lab-validate.sh
./platform/scripts/lab-plan.sh
./platform/scripts/lab-plan.sh --phase docker-web-api
```

`lab-plan.sh` distingue ambientes já catalogados (`CATALOGUED`) de ambientes ainda por implementar (`PLANNED`).

## Fases de expansão

1. Baseline, catálogo e Juice Shop end-to-end.
2. Web e API em Docker.
3. DevSecOps, supply chain e IA/MCP.
4. Kubernetes com kind/k3d.
5. Máquinas virtuais, infraestrutura, redes e Active Directory.
6. Cloud sandbox, mobile, IoT, firmware e OT/ICS.

A execução normal não concede egress permanente, não publica ambientes na LAN e liga o Kali apenas à rede do laboratório ativo. O Kali deve ser desligado dessa rede no final de cada execução.

## Fluxo de alteração

```text
issue → branch → commit → pull request → CI → revisão → merge → deployment local → evidências
```

Não existe deployment automático do GitHub para o Hermes nem self-hosted runner com acesso ao Docker socket.
