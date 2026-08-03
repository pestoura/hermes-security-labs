# Mapeamento versionado de runbooks API — famílias, perfis e critérios

Versão: `2026-08-03`
Head base: `9a43c065d27d3247ccd6679f015d501730d19836`
Head final alvo: `9a43c065d27d3247ccd6679f015d501730d19836` (sem alterações do repositório antes desta operação; alterações futuras são commits adicionais)

## Objetivo

Substituir placeholders genéricos e correções superficiais por critérios semanticamente corretos e executáveis nos runbooks do pacote `api`.

## Famílias funcionais

- `authentication`: provar identidade; sinais centrais `auth.accepted`, `auth.scheme`, `jwt.*`, `response_status`.
- `authorization`: controlo por objeto/função/propriedade/escopo/tenant; sinais centrais `object.owner_id`, `subject.id`, `response_status`, `response.contains_sensitive_data`.
- `token-session`: tempo de vida, fixação, logout, cookies; sinais `jwt.claims.exp`, `jwt.claims.aud`, `token.invalidated`, `set-cookie`.
- `transport`: TLS/certificados/HSTS/plaintext; sinais `tls.*`, `response_status`, `response_headers`.
- `rate-resource`: rate-limit, tamanho, custo; sinais `rate_limit.triggered`, `response_status`, `response_bytes`.
- `input-validation`: injeção, upload, SSRF, path traversal; sinais `request.redirect_target`, `upload.executed`, `response_status`, `response.contains_sensitive_data`.
- `data-exposure`: PII, segredos, stacktrace, debug; sinais `response.contains_sensitive_data`, `response_headers`, `response_status`.
- `discovery`: endpoints, GraphQL, backup, gateway; sinais `response_status`, `response_contains_schema`, `openapi_security_schemes_present`.
- `business-logic`: idempotency, race, inventário, estado; sinais `response_status`, `entity.id`, `entity.owner_id`.
- `configuration`: CORS, headers, credenciais, debug, host-trust; sinais `response_headers`, `response_status`.

## Sinais normalizados admissíveis

Sinais produzidos diretamente pelo runner/handler/campanha:
- `response_status`
- `response_headers`
- `response.contains_sensitive_data`
- `response_contains_schema`
- `request.redirect_target`
- `upload.executed`
- `auth.accepted`
- `auth.scheme`
- `jwt.signature.valid`
- `jwt.claims.aud`
- `jwt.claims.exp`
- `jwt.claims.iss`
- `jwt.claims.sub`
- `jwt.alg`
- `jwt.secret_bits`
- `object.owner_id`
- `subject.id`
- `entity.id`
- `entity.owner_id`
- `rate_limit.triggered`
- `tls.cert_expired`
- `tls.hostname_mismatch`
- `tls.weak_ciphers`
- `tls.plaintext_allowed`
- `openapi_security_schemes_present`
- `target_reachable`
- `prerequisites_missing`
- `handler_signal` — apenas quando documentado e estável por handler.

Regra: critérios não devem referir-se a sinais que o handler/profile não pode produzir.

## Critérios mínimos por família

Cada runbook tem `vulnerable_when`, `secure_when` e `inconclusive_when` baseados apenas em sinais acima.
Em comum:
- `inconclusive_when: [target_reachable == false or prerequisites_missing == true]` é permitido como fallback genérico.
- Critérios não devem usar `workflow_status` como proxy universal.

## Mapeamento runbook -> família, sinais e critérios

Documento canónico futuro: gerar `security/docs/api-runbook-mapping.csv` a partir de catálogo + yaml.

Exemplos representativos:

| runbook | handler/profile | família | sinais | regra vulnerable | regra secure | regra inconclusive |
|---|---|---|---|---|---|---|
| API-AUTH-JWT-AUDIENCE-008 | jwt/jwt-audience-validation | authentication | jwt.claims.aud, response_status | aud ausente ou mismatch contra emissor conhecido | aud presente e coincide com o publicador | target_reachable==false |
| API-AUTH-MISSING-001 | http/missing-authentication | authentication | response_status, auth.accepted, auth.scheme | resposta 200 sem nenhum esquema de auth aceite | 401/403 ou esquema auth presente | target_reachable==false |
| API-AUTH-BASIC-TRANSPORT-016 | http/basic-auth-transport | authentication | response_status, request.redirect_target, response_headers | esquema basic em HTTP sem HSTS e permite downgrade | apenas HTTPS ou redirecionamento para HTTPS com HSTS | target_reachable==false |
| API-AUTHZ-BOLA-READ-001 | http/bola-read | authorization | response_status, object.owner_id, subject.id | 200 com objeto de outro owner sem validação | 403/404 quando owner != caller | target_reachable==false |
| API-AUTHZ-MASS-OWNER-012 | http/mass-assignment-owner | authorization | response_status, response.contains_sensitive_data, object.owner_id | 200 e owner_id alterado sem token de autorização | owner_id permanece inalterado | target_reachable==false |

## Critérios determinísticos para exemplos anteriormente incorretos

### API-AUTH-JWT-AUDIENCE-008
```yaml
evaluation:
  vulnerable_when:
  - jwt.claims.aud is null or jwt.claims.aud not in {'hex0r-api','crapi'}
  secure_when:
  - jwt.claims.aud in {'hex0r-api','crapi'} and jwt.signature.valid == true
  inconclusive_when:
  - target_reachable == false or prerequisites_missing == true
```

### API-AUTH-MISSING-001
```yaml
evaluation:
  vulnerable_when:
  - auth.accepted == false and response_status == 200
  secure_when:
  - auth.accepted == true or response_status in {401,403}
  inconclusive_when:
  - target_reachable == false or prerequisites_missing == true
```

### API-AUTH-BASIC-TRANSPORT-016
```yaml
evaluation:
  vulnerable_when:
  - auth.scheme == 'basic' and request.redirect_target != '' and request.redirect_target startswith 'http://'
  secure_when:
  - request.redirect_target == '' or request.redirect_target startswith 'https://'
  inconclusive_when:
  - target_reachable == false or prerequisites_missing == true
```

## Aceitação

- `securityctl validate` sem warnings nem errors.
- Testes que provam fixture vulnerável => vulnerable; fixture segura => secure/non-vulnerable; dados insuficientes => inconclusive; sinais de uma família não ativam outra família.

## Notas

- Não usar `workflow_status in {'failed','blocked'}` como substituto de deteção técnica.
- Não usar headers irrelevantes como proxy para famílias distintas.
