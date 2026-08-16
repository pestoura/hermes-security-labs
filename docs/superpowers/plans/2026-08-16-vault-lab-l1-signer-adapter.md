# VAULT LAB_L1 Signer Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a fail-closed LAB_L1 Vault Transit Ed25519 signer behind the existing provider-neutral `SigningService`, with AppRole machine authentication, exact key/version/public identity validation, deterministic audit identity, no local-key fallback, and no trust/runtime promotion.

**Architecture:** Keep the existing `SigningService` protocol unchanged. Move the already-existing domain-separated verification payload into the provider-neutral contract, add a small HTTPS Vault transport, then implement `VaultAuthSession` and `VaultSignerAdapter` as provider-specific components behind the contract. The adapter observes one non-exportable Ed25519 Transit key, pins the exact observed version into the sign request, converts only public metadata into `SigningResult`, and emits a content-addressed `audit_ref` that is an object identity only; canonical signer-audit Evidence Plane custody remains a separate verifier-backed gate.

**Tech Stack:** Python 3, pytest, Python standard-library `urllib.request`/`ssl`/`json`, `cryptography` for public-key/SPKI normalization, existing `platform/assurance/signing_service.py`, existing signer audit/Evidence Plane contracts, GitHub Actions.

## Global Constraints

- Implement the owner-approved Option A from `docs/superpowers/specs/2026-08-16-vault-lab-l1-operational-implementation-design.md`.
- Scope is LAB_L1 only; this change does not provision or select a production supplier.
- First implementation supports exactly `Ed25519`; `ECDSA-P256-SHA256` remains provider-neutral contract capability but is out of scope for CHG-HSL-081.
- Preserve the existing `SigningService.sign(SigningRequest) -> SigningResult` protocol unchanged.
- Canonical signed bytes must remain the exact domain-separated bytes already used by `TestSignerAdapter`; no provider may sign only the naked SHA-256 field.
- Vault Transit key must be observed as `type=ed25519`, `supports_signing=true`, `derived=false`, `exportable=false`, `allow_plaintext_backup=false` before signing is accepted.
- The exact observed Transit key version must be supplied as `key_version` in the sign request and must equal the version encoded in the returned `vault:v<version>:<base64>` signature.
- Vault credentials/tokens never enter Git, `SigningResult`, audit records, evidence records, exception messages or logs.
- AppRole credentials are resolved through injected references; the adapter receives no root/admin token and cannot create/rotate/delete keys, mutate policies, auth methods or mounts.
- The concrete transport accepts HTTPS Vault base URLs only; disposable insecure/dev-mode integration is not part of this change.
- No request retry loop. At most one bounded AppRole re-authentication may occur after an authentication-class response; a second failure returns HOLD/fail-closed.
- No local PEM/OpenSSL/TestSigner fallback exists.
- `audit_ref=evidence://vault-sign-operation/<sha256>` is a deterministic sanitized operation-object identity, not Evidence Plane custody proof and not trust binding.
- Existing signer audit/Evidence Plane custody contracts remain the canonical independent proof path; no second datastore, chain, seal, verifier or ledger is introduced.
- Do not change `platform/assurance/signer-human-decision.yaml` from `NO_DECISION`.
- Preserve `supplier_selection=NO_SELECTION`, `selected_class=null`, `human_decision_id=null`, trust absent/unbound, `promotion_allowed=false`, `runtime_status=NOT_RUN`, `execution_authority=NONE`, campaign `BLOCKED/HOLD`.
- Do not enable receipt delivery, signer custody policy, trust installation, PRE_PROMOTION, HITL or any Runner/Kali/target effect.
- Strict TDD: observe a tests-first RED before creating production adapter/transport code.
- Exact-SHA validation is mandatory on the final PR head and post-merge main before declaring completion.

---

### Task 1: Reserve CHG-HSL-081 and create the tests-first contract

**Files:**
- Create: `changes/CHG-HSL-081.yaml`
- Create: `platform/tests/test_vault_signer_adapter.py`
- Create: `platform/tests/test_vault_transport.py`
- Modify later: `platform/assurance/signing_service.py`
- Create later: `platform/assurance/vault_transport.py`
- Create later: `platform/assurance/vault_signer_adapter.py`

**Interfaces:**
- Existing: `SigningRequest`, `SigningResult`, `SigningServiceError`, `validate_signing_request()`.
- Expects Task 2 to produce: `canonical_signing_payload(request) -> bytes`.
- Expects Task 3 to produce: `VaultHttpResponse`, `VaultTransportError`, `VaultTransport`, `UrllibVaultTransport`.
- Expects Task 4 to produce: `VaultSignerConfig`, `SecretResolver`, `VaultAuthSession`, `VaultSignerAdapter`, `VaultSignerError`.

- [ ] **Step 1: Add the change record without claiming success**

Create `changes/CHG-HSL-081.yaml`:

```yaml
schemaVersion: jds.change/v1
kind: ChangeRecord
id: CHG-HSL-081
product: hermes-security-labs
classification: HARDENING
state: IMPLEMENTING
disposition: FIX_NOW
summary: 'Implement the first fail-closed LAB_L1 Vault Transit Ed25519 signer adapter behind the provider-neutral SigningService without selecting trust, enabling runtime policy or promoting the campaign.'
source:
  type: ENGINEERING_REVIEW
  campaign: VAL-HSL-RUNNER-L1-LIVE-PROMOTION
  observation: OBS-LAB-L1-VAULT-SIGNER
  reference: 'Issue #420 / ADR-0014 / owner-approved 2026-08-16 Vault operational design. Implementation authorization is not evidence-bearing APPROVED/SELECTED state.'
affectedRelease: jds-002-adoption-candidate
targetRelease: null
risk: MEDIUM
versionEffect: NONE
branch: chg-hsl-081/vault-lab-l1-signer-adapter
issue: 420
pr: null
validation:
  targeted: NOT_RUN
  regression: NOT_RUN
  security: NOT_RUN
  runtime: NOT_RUN
promotion:
  commit: null
  artifactDigest: null
  previousRelease: null
deferredTo: null
timestamps:
  discoveredAt: '2026-08-16T14:15:00Z'
  updatedAt: '2026-08-16T14:15:00Z'
  closedAt: null
```

- [ ] **Step 2: Write tests requiring a canonical provider-neutral signing payload**

Extend the dynamic-import pattern used in `platform/tests/test_signing_service.py` and require:

```python
def test_canonical_signing_payload_is_domain_separated_and_deterministic() -> None:
    signing = _signing()
    request = signing.SigningRequest(
        digest_sha256="a" * 64,
        purpose="tb1-authorization",
        domain="hex0r.tb1.authorization.v1",
        correlation_id="corr-081",
    )
    expected = b"\x00".join(
        (
            b"HSL-SIGNING-V1",
            b"hex0r.tb1.authorization.v1",
            b"tb1-authorization",
            b"corr-081",
            bytes.fromhex("a" * 64),
        )
    )
    assert signing.canonical_signing_payload(request) == expected
    assert signing.canonical_signing_payload(request) == expected
```

Add a regression assertion that `TestSignerAdapter` still verifies over those exact bytes rather than a new provider-specific representation.

- [ ] **Step 3: Write failing Vault adapter tests before the files exist**

`platform/tests/test_vault_signer_adapter.py` must dynamically load the future file and start with helpers like:

```python
ROOT = Path(__file__).resolve().parents[2]
ASSURANCE = ROOT / "platform" / "assurance"
VAULT_ADAPTER_PATH = ASSURANCE / "vault_signer_adapter.py"
VAULT_TRANSPORT_PATH = ASSURANCE / "vault_transport.py"


def _vault():
    assert VAULT_ADAPTER_PATH.exists(), "vault_signer_adapter.py is not implemented yet"
    return _load(VAULT_ADAPTER_PATH, "chg_hsl_081_vault_signer")
```

The first test set must require at least:

```python
def test_config_contains_references_not_credentials() -> None:
    vault = _vault()
    config = vault.VaultSignerConfig(
        vault_addr="https://vault.internal:8200",
        transit_mount="transit",
        key_name="hsl-lab-l1",
        approle_mount="approle",
        role_id_ref="secretref://vault/lab-l1/role-id",
        secret_id_ref="secretref://vault/lab-l1/secret-id",
        expected_algorithm="Ed25519",
        namespace=None,
        timeout_seconds=3.0,
    )
    text = repr(config)
    assert "role_id=" not in text
    assert "secret_id=" not in text
    assert "token=" not in text
```

```python
def test_invalid_signing_request_is_rejected_before_any_transport_call() -> None:
    vault, signing = _modules()
    transport = FakeTransport()
    adapter = _adapter(transport)
    request = signing.SigningRequest(
        digest_sha256="A" * 64,
        purpose="tb1-authorization",
        domain="hex0r.tb1.authorization.v1",
        correlation_id="corr-081",
    )
    with pytest.raises(signing.SigningServiceError):
        adapter.sign(request)
    assert transport.calls == []
```

```python
def test_adapter_pins_observed_key_version_and_returns_public_only_result() -> None:
    vault, signing = _modules()
    transport = FakeTransport.sequence(
        approle_login(token="vault-token-redacted"),
        ed25519_key_metadata(version=3, exportable=False, backup=False),
        vault_signature(version=3),
    )
    result = _adapter(transport).sign(_request(signing))
    sign_call = transport.calls[-1]
    assert sign_call.path == "/v1/transit/sign/hsl-lab-l1"
    assert sign_call.json_body["key_version"] == 3
    assert result.signer_class == "VAULT"
    assert result.algorithm == "Ed25519"
    assert result.admissible_for_lab_l1 is True
    assert result.audit_ref.startswith("evidence://vault-sign-operation/")
    assert not hasattr(result, "token")
    assert "vault-token-redacted" not in repr(result)
```

Add negative tests for: `exportable=true`, `allow_plaintext_backup=true`, `derived=true`, `supports_signing=false`, wrong key name, wrong type, absent/malformed public key, wrong returned signature version, malformed signature base64, auth refusal, permission denial, timeout, malformed JSON, and a second auth failure after one bounded re-authentication.

- [ ] **Step 4: Write failing transport tests**

`platform/tests/test_vault_transport.py` must require:

- HTTPS base URL only;
- no userinfo/query/fragment in `vault_addr`;
- paths constrained to `/v1/...` and reject `..` traversal;
- methods restricted to `GET`/`POST`;
- TLS verification enabled with default CA or configured CA bundle;
- bounded timeout;
- JSON request/response only;
- maximum response size;
- stable errors that never include response body, `X-Vault-Token`, RoleID or SecretID.

- [ ] **Step 5: Push the tests-first head and observe RED**

Expected RED causes must be limited to the intentionally absent provider implementation and payload helper, for example:

```text
vault_signer_adapter.py is not implemented yet
vault_transport.py is not implemented yet
canonical_signing_payload is missing
```

No unrelated regression is acceptable as RED evidence.

- [ ] **Step 6: Record the RED checkpoint**

Create `docs/superpowers/checkpoints/CHG-HSL-081-tests-first.md` with exact branch head SHA, CI run/jobs, failure counts and confirmation that the failures are limited to the intended missing implementation.

- [ ] **Step 7: Commit tests-first checkpoint**

```bash
git add changes/CHG-HSL-081.yaml platform/tests/test_vault_signer_adapter.py platform/tests/test_vault_transport.py platform/tests/test_signing_service.py docs/superpowers/checkpoints/CHG-HSL-081-tests-first.md
git commit -m "test(chg-hsl-081): define Vault signer contract"
```

---

### Task 2: Canonicalize the shared TB1 signing payload without changing `SigningService`

**Files:**
- Modify: `platform/assurance/signing_service.py`
- Modify: `platform/assurance/test_signer_adapter.py`
- Modify: `platform/tests/test_signing_service.py`

**Interfaces:**
- Produces: `canonical_signing_payload(request: SigningRequest) -> bytes`.
- `SigningService` protocol remains exactly one public method: `sign`.

- [ ] **Step 1: Add the canonical helper after request validation**

Implement exactly the current domain separation already used by the CI signer:

```python
def canonical_signing_payload(request: SigningRequest) -> bytes:
    request = validate_signing_request(request)
    return b"\x00".join(
        (
            b"HSL-SIGNING-V1",
            request.domain.encode("utf-8"),
            request.purpose.encode("utf-8"),
            request.correlation_id.encode("utf-8"),
            bytes.fromhex(request.digest_sha256),
        )
    )
```

- [ ] **Step 2: Remove duplicate payload logic from `TestSignerAdapter`**

Keep the public compatibility helper but delegate it:

```python
def verification_payload(request) -> bytes:
    return _signing.canonical_signing_payload(request)
```

- [ ] **Step 3: Run focused signing-service regression**

```bash
pytest -q platform/tests/test_signing_service.py platform/tests/test_test_signer_adapter.py
```

Expected: PASS, with existing deterministic Ed25519 signatures unchanged for identical inputs.

- [ ] **Step 4: Commit the provider-neutral refactor**

```bash
git add platform/assurance/signing_service.py platform/assurance/test_signer_adapter.py platform/tests/test_signing_service.py
git commit -m "refactor(chg-hsl-081): canonicalize signing payload"
```

---

### Task 3: Implement the bounded HTTPS Vault transport

**Files:**
- Create: `platform/assurance/vault_transport.py`
- Test: `platform/tests/test_vault_transport.py`

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class VaultHttpResponse:
    status_code: int
    body: Mapping[str, object]
    request_id: str | None

class VaultTransportError(RuntimeError):
    code: str
    status_code: int | None

class VaultTransport(Protocol):
    def request(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        json_body: Mapping[str, object] | None = None,
    ) -> VaultHttpResponse: ...
```

- [ ] **Step 1: Validate construction and URL/path boundaries**

Use `urllib.parse.urlsplit`. Accept only `https`, non-empty host, no username/password, query or fragment. Normalize the base URL by removing one trailing slash. Reject paths not beginning `/v1/`, any `..` path segment, control characters, query or fragment in the relative path.

- [ ] **Step 2: Implement TLS-verified standard-library HTTP requests**

Use `ssl.create_default_context(cafile=ca_bundle_path or None)` and `urllib.request.Request`/`urlopen`. Do not create an unverified SSL context. JSON must be canonical compact UTF-8:

```python
payload = json.dumps(
    dict(json_body), sort_keys=True, separators=(",", ":"), ensure_ascii=True
).encode("utf-8")
```

Set `Content-Type: application/json` only for a request body and `Accept: application/json` for all requests. Allow caller headers only from a closed set required by Vault (`X-Vault-Token`, `X-Vault-Namespace`); reject CR/LF/control characters.

- [ ] **Step 3: Bound response processing and sanitize all errors**

Read at most `262_145` bytes and reject any response above 256 KiB. Map failures to stable codes without including body/header/credential values:

```text
VAULT_TRANSPORT_TIMEOUT
VAULT_TRANSPORT_TLS_FAILED
VAULT_TRANSPORT_UNREACHABLE
VAULT_TRANSPORT_HTTP_ERROR
VAULT_TRANSPORT_RESPONSE_TOO_LARGE
VAULT_TRANSPORT_RESPONSE_INVALID
VAULT_TRANSPORT_REQUEST_INVALID
```

`VaultTransportError.__str__()` may identify only the stable code and numeric HTTP status.

- [ ] **Step 4: Run focused transport tests**

```bash
pytest -q platform/tests/test_vault_transport.py
```

Expected: PASS.

- [ ] **Step 5: Commit transport GREEN**

```bash
git add platform/assurance/vault_transport.py platform/tests/test_vault_transport.py
git commit -m "feat(chg-hsl-081): add bounded Vault transport"
```

---

### Task 4: Implement AppRole session and exact Ed25519 Transit key observation

**Files:**
- Create: `platform/assurance/vault_signer_adapter.py`
- Test: `platform/tests/test_vault_signer_adapter.py`

**Interfaces:**
- Produces:

```python
class VaultSignerError(ValueError):
    code: str

@dataclass(frozen=True)
class VaultSignerConfig:
    vault_addr: str
    transit_mount: str
    key_name: str
    approle_mount: str
    role_id_ref: str
    secret_id_ref: str
    expected_algorithm: str = "Ed25519"
    namespace: str | None = None
    timeout_seconds: float = 3.0
    ca_bundle_path: str | None = None

class SecretResolver(Protocol):
    def resolve(self, reference: str) -> str: ...

@dataclass(frozen=True)
class VaultKeyObservation:
    key_name: str
    key_version: int
    vault_type: str
    algorithm: str
    public_key_spki_sha256: str
    exportable: bool
    allow_plaintext_backup: bool
    supports_signing: bool

class VaultAuthSession:
    def token(self) -> str: ...
    def invalidate(self) -> None: ...
```

- [ ] **Step 1: Implement strict config validation**

Constraints:

- `transit_mount`, `approle_mount`, `key_name`: `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`;
- references: printable non-empty strings `<=512`, no embedded credential values;
- namespace when present: printable, no control characters, `<=256`;
- timeout: numeric `0.25..30.0`, bool forbidden;
- `expected_algorithm` must equal `Ed25519` in CHG-HSL-081;
- `repr(config)` must not expose resolved credentials because config stores references only.

- [ ] **Step 2: Implement AppRole login using the injected resolver and transport**

Resolve RoleID and SecretID only immediately before login, validate them as bounded strings, call:

```text
POST /v1/auth/<approle_mount>/login
```

with:

```python
{"role_id": role_id, "secret_id": secret_id}
```

Require `auth.client_token` to be non-empty and bounded. Cache only the token string in process memory. Do not expose token, RoleID or SecretID via repr, exceptions or public properties.

- [ ] **Step 3: Implement key metadata observation before signing**

Call:

```text
GET /v1/<transit_mount>/keys/<key_name>
```

using the AppRole token. Require exact public state:

```python
data["name"] == config.key_name
data["type"] == "ed25519"
data["supports_signing"] is True
data["derived"] is False
data["exportable"] is False
data["allow_plaintext_backup"] is False
```

Determine the highest numeric key version from `data["keys"]`. For that version require an asymmetric public-key value from the provider response. Normalize it with `cryptography` into DER SubjectPublicKeyInfo and compute:

```python
spki_sha256 = hashlib.sha256(public_der).hexdigest()
```

Accept only a real Ed25519 public key object after parsing. Do not use Transit key export because the LAB_L1 key must remain non-exportable.

- [ ] **Step 4: Map auth/provider failures without leaking provider text**

Stable adapter codes:

```text
VAULT_CONFIG_INVALID
VAULT_SECRET_RESOLUTION_FAILED
VAULT_AUTH_FAILED
VAULT_ACCESS_DENIED
VAULT_UNAVAILABLE
VAULT_KEY_OBSERVATION_FAILED
VAULT_KEY_NOT_ADMISSIBLE
VAULT_KEY_IDENTITY_INVALID
VAULT_SIGN_FAILED
VAULT_SIGN_RESPONSE_INVALID
VAULT_AUDIT_IDENTITY_FAILED
```

A transport exception is translated from its class/code/status only; never include Vault response bodies.

- [ ] **Step 5: Run focused auth/key-observation tests**

```bash
pytest -q platform/tests/test_vault_signer_adapter.py -k "config or auth or key"
```

Expected: PASS.

- [ ] **Step 6: Commit auth/key observation GREEN**

```bash
git add platform/assurance/vault_signer_adapter.py platform/tests/test_vault_signer_adapter.py
git commit -m "feat(chg-hsl-081): observe admissible Vault signing key"
```

---

### Task 5: Implement exact-version Vault Transit signing and deterministic audit identity

**Files:**
- Modify: `platform/assurance/vault_signer_adapter.py`
- Modify: `platform/tests/test_vault_signer_adapter.py`
- Reuse: `platform/assurance/signing_service.py`

**Interfaces:**
- `VaultSignerAdapter.sign(request: SigningRequest) -> SigningResult`.
- `VaultSignerAdapter` implements the existing provider-neutral protocol structurally; no new method is added to `SigningService`.

- [ ] **Step 1: Sign the canonical domain-separated payload**

After `validate_signing_request()` and exact key observation:

```python
payload = _signing.canonical_signing_payload(request)
input_b64 = base64.b64encode(payload).decode("ascii")
```

Call:

```text
POST /v1/<transit_mount>/sign/<key_name>
```

with exactly:

```python
{
    "input": input_b64,
    "key_version": observation.key_version,
}
```

For Ed25519 do not set provider hash/prehashed options; the exact domain-separated bytes are the message.

- [ ] **Step 2: Parse and bind the exact returned version**

Require the response signature format:

```text
vault:v<positive integer>:<canonical base64>
```

The returned version must equal `observation.key_version`. Decode the signature payload and require exactly 64 Ed25519 signature bytes. Return only standard base64 of the raw signature in `SigningResult.signature_b64`; do not expose the `vault:vN:` wrapper above the adapter.

- [ ] **Step 3: Build a sanitized content-addressed operation identity**

Construct a closed public object containing only:

```python
{
    "schema_version": "vault-sign-operation/v1",
    "provider": "vault-transit",
    "key_name": observation.key_name,
    "key_version": observation.key_version,
    "algorithm": "Ed25519",
    "public_key_spki_sha256": observation.public_key_spki_sha256,
    "request_digest_sha256": request.digest_sha256,
    "purpose": request.purpose,
    "domain": request.domain,
    "correlation_id": request.correlation_id,
    "signature_sha256": hashlib.sha256(signature_bytes).hexdigest(),
    "promotion_allowed": False,
    "runtime_status": "NOT_RUN",
    "execution_authority": "NONE",
}
```

Canonicalize with sorted compact JSON and derive:

```python
audit_ref = f"evidence://vault-sign-operation/{hashlib.sha256(canonical).hexdigest()}"
```

This is object identity only. It must not be represented as Evidence Plane verification, trust installation or R1-R8 proof.

- [ ] **Step 4: Return the provider-neutral result**

```python
return _signing.SigningResult(
    signature_b64=base64.b64encode(signature_bytes).decode("ascii"),
    key_id=f"vault:{config.transit_mount}:{config.key_name}:v{observation.key_version}",
    algorithm="Ed25519",
    public_key_spki_sha256=observation.public_key_spki_sha256,
    signer_class="VAULT",
    authority="EXTERNAL_CUSTODY",
    admissible_for_lab_l1=True,
    audit_ref=audit_ref,
)
```

Then call `_signing.require_lab_l1_admissible(result)` before returning. This remains only the structural envelope guard.

- [ ] **Step 5: Implement one bounded re-authentication path**

If a token-authenticated key-read/sign call returns an authentication-class failure, invalidate the cached token, authenticate once and replay the single failed provider operation once. Any second auth failure is terminal. Permission denial after re-authentication is terminal and no further retry occurs.

- [ ] **Step 6: Run all Vault adapter tests**

```bash
pytest -q platform/tests/test_vault_signer_adapter.py platform/tests/test_vault_transport.py
```

Expected: PASS.

- [ ] **Step 7: Commit signing GREEN**

```bash
git add platform/assurance/vault_signer_adapter.py platform/tests/test_vault_signer_adapter.py
git commit -m "feat(chg-hsl-081): sign TB1 payloads with Vault Transit"
```

---

### Task 6: Prove compatibility with canonical signer audit and protect governance boundaries

**Files:**
- Create: `platform/tests/test_vault_signer_audit_integration.py`
- Reference: `platform/assurance/signer_audit_adapter.py`
- Reference: `platform/evidence-plane/signer_audit_custody.py`
- Reference: `platform/assurance/signer-human-decision.yaml`
- Reference: `validation/VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml`

**Interfaces:**
- Consumes: real `VaultSignerAdapter` with fake transport only, `build_signer_audit_record(...)`, `signer_record_digest(...)`.
- No production audit/custody contract is modified unless a test exposes a genuine incompatibility.

- [ ] **Step 1: Add a cross-contract integration test**

Use fake Vault responses to produce one real `SigningResult`, then pass it through the existing signer audit builder:

```python
result = vault_adapter.sign(request)
record = signer_audit.build_signer_audit_record(
    request,
    result,
    signer_audit.SignerAuditAttribution(
        principal="hermes-assurance",
        provider_ref="vault-transit/lab-l1",
        test_only=False,
    ),
)
assert record["signer_class"] == "VAULT"
assert record["test_only"] is False
assert record["promotion_allowed"] is False
assert record["runtime_status"] == "NOT_RUN"
assert record["execution_authority"] == "NONE"
```

Assert the serialized record and audit identity do not contain the fake Vault token, RoleID or SecretID.

- [ ] **Step 2: Add source-of-truth guard assertions**

Require:

```python
assert signer_decision["decision"]["state"] == "NO_DECISION"
assert signer_decision["decision"]["selected_class"] is None
assert signer_decision["decision"]["human_decision_id"] is None
assert campaign["state"] == "BLOCKED"
assert campaign["promotionRecommendation"] == "HOLD"
```

Do not rewrite these files in this change.

- [ ] **Step 3: Run signer/evidence regressions**

```bash
pytest -q \
  platform/tests/test_signing_service.py \
  platform/tests/test_test_signer_adapter.py \
  platform/tests/test_signer_audit_adapter.py \
  platform/tests/test_signer_audit_evidence_verifier.py \
  platform/tests/test_vault_transport.py \
  platform/tests/test_vault_signer_adapter.py \
  platform/tests/test_vault_signer_audit_integration.py
```

Expected: PASS.

- [ ] **Step 4: Commit compatibility hardening**

```bash
git add platform/tests/test_vault_signer_audit_integration.py
git commit -m "test(chg-hsl-081): bind Vault signer to canonical audit contracts"
```

---

### Task 7: Security hardening and repository-wide validation

**Files:**
- Modify tests/implementation only for defects found by this gate.
- Update: `changes/CHG-HSL-081.yaml` only after evidence is observed.

**Interfaces:**
- No new runtime interface.

- [ ] **Step 1: Run AST/static assertions**

Tests must prove:

- `signing_service.py` still imports no provider/network client;
- `vault_signer_adapter.py` imports no `subprocess`, Docker API, filesystem private-key loader or test signer fallback;
- no call path includes Transit create/rotate/delete/config/policy/auth-management endpoints;
- no string `VAULT_TOKEN`, `root token`, PEM private-key header or example real credential exists in changed source/test artifacts.

- [ ] **Step 2: Run full platform regression**

```bash
pytest -q platform/tests
```

Expected: all platform tests PASS, with only repository-canonical skips.

- [ ] **Step 3: Run repository governance/security suites**

Use the repository-canonical commands/workflows that produced the CHG-HSL-080 evidence:

```text
validate
security
Release governance
Private VAmPI source-repo access deny
Exact-SHA validation evidence
```

All must be GREEN on the same candidate SHA.

- [ ] **Step 4: Update change record to accepted only after exact evidence exists**

Set:

```yaml
state: ACCEPTED
validation:
  targeted: PASS
  regression: PASS
  security: PASS
  runtime: NOT_RUN
promotion:
  commit: null
```

Do not record a runtime PASS and do not populate promotion commit/artifact digest.

- [ ] **Step 5: Update provider-neutral signer status documentation**

Append CHG-HSL-081 as `GREEN-REPO` implementation capability while explicitly preserving:

```text
operational human signer decision = NO_DECISION
supplier_selection = NO_SELECTION
provider live attestation = NOT_OBSERVED
trust = ABSENT/UNBOUND
campaign = BLOCKED/HOLD
```

- [ ] **Step 6: Commit final candidate**

```bash
git add changes/CHG-HSL-081.yaml docs/roadmap/provider-neutral-signer-boundary-2026-08-15.md
git commit -m "docs(chg-hsl-081): record Vault signer validation"
```

---

### Task 8: PR, exact-SHA merge and post-merge proof

**Files:**
- GitHub issue #420
- CHG-HSL-081 PR
- No additional runtime files unless a CI defect requires correction.

**Interfaces:**
- Candidate SHA is immutable for the final CI gate.

- [ ] **Step 1: Create/update the PR**

PR title:

```text
CHG-HSL-081: implement LAB_L1 Vault Transit signer adapter
```

PR body must include:

- owner-approved design path;
- issue #420;
- tests-first RED evidence;
- focused GREEN evidence;
- full regression/security/governance counts;
- exact candidate SHA;
- explicit statement that no Vault service/key was provisioned and no trust/runtime promotion occurred.

- [ ] **Step 2: Require all protected workflows GREEN on the exact PR head**

Do not merge based on an earlier SHA. Require the same four protected workflows plus Exact-SHA evidence on the final head.

- [ ] **Step 3: Merge under branch protection**

Use expected-head protection and the repository's established squash-merge convention.

- [ ] **Step 4: Re-run/observe post-merge main exact-SHA gates**

Require `validate`, `security`, `Release governance`, `Private VAmPI source-repo access deny` and Exact-SHA GREEN on the resulting main commit.

- [ ] **Step 5: Close #420 only after post-merge GREEN**

Comment the exact merged main SHA, test counts and operational state. Close as `completed` while leaving #403 open until evidence-backed human decision criteria are actually satisfied.

## Plan self-review

- Spec coverage: configuration, AppRole, transport, signing, exact key/version/public identity, audit handoff, secret sanitization, negative behavior, governance and exact-SHA gates are covered.
- Scope reduction: first slice is Ed25519 only; ECDSA and disposable/live Vault provisioning are intentionally excluded rather than partially implemented.
- No placeholders: implementation signatures, file paths, stable errors, payload structures and test commands are explicit.
- Type consistency: `SigningService` remains unchanged; Vault-specific types exist only behind it; `SigningResult` fields match the existing canonical contract.
- Security boundary: no key export, no local fallback, no trust binding, no runtime authority, no target interaction.
