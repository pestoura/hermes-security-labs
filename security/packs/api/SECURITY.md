# Security policy

Este projeto contém automação de testes de segurança de uso dual. A utilização é permitida apenas em ambientes próprios ou com autorização explícita e âmbito documentado.

## Controlos obrigatórios

- allowlist de hosts/CIDR em todas as execuções;
- egress desativado por defeito nos laboratórios;
- limites de pedidos, timeout, concorrência e tamanho de resposta;
- confirmação separada para ações destrutivas;
- credenciais por referência e redaction de cabeçalhos sensíveis;
- logs de auditoria sem tokens, cookies ou corpos completos;
- kill switch por campanha;
- runner sem `shell=True` e sem comandos arbitrários.

## Reporting

Não publiques vulnerabilidades de terceiros, dados pessoais, credenciais ou evidências não sanitizadas em issues. Usa um canal privado para reportar problemas de segurança no próprio projeto.

## Supported status

Apenas runbooks com `metadata.status: stable` devem ser considerados validados. `experimental` significa que o contrato existe, mas a deteção e os limites ainda têm de ser calibrados em laboratório.
