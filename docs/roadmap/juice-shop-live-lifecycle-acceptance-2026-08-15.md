# Juice Shop live lifecycle acceptance — 2026-08-15

**Change:** `CHG-HSL-070`  
**Issue:** `#394`  
**Accepted runtime run:** `run_cc3cd41e85c44d9182305960ea816f18`  
**Prior FAIL run (retained, not reclassified):** `run_353c8079eca84a90be30d4a3324af451`  
**Evidence-manifest run:** `run_8fbe0ad257fb4252ad9797c9e913ad6b`  
**Repository revision exercised:** `2b793750e95f0d0a9a8ac4b82e1b684cc7732e19`  
**Scope:** local OWASP Juice Shop lifecycle only  
**Disposition:** `PASS / ACCEPTED-LIVE-LIFECYCLE` (attempt 2 accepted; attempt 1 retained as FAIL)

This record persists the sanitised acceptance result for the Juice Shop lifecycle. It does **not** authorize Runner promotion, signer/trust activation, Kali target traffic, exploitation or any other lab. No Runner authority is granted by this acceptance.

## Attempt 1 — FAIL (retained, never reclassified as PASS)

Run `run_353c8079eca84a90be30d4a3324af451` executed on the exact SHA `2b793750e95f0d0a9a8ac4b82e1b684cc7732e19`. The functional lifecycle (start/status/smoke/reset/destroy) and cleanup all succeeded, but acceptance is **FAIL** for the high-port gate: the sanitized execution harness accidentally removed the intentional `JUICE_SHOP_HOST_PORT` variable, so the clean rerun bound the default `127.0.0.1:3000` instead of the selected high port `14300`.

Cleanup in attempt 1 remained `PASS` / idempotent / zero-residue. This attempt is recorded as FAIL and is **not** reclassified as PASS by the accepted attempt 2.

## Attempt 2 — ACCEPTED PASS candidate

Run `run_cc3cd41e85c44d9182305960ea816f18` executed on the exact SHA `2b793750e95f0d0a9a8ac4b82e1b684cc7732e19`.

### Explicit environment contract

`JUICE_SHOP_HOST_PORT=14300` was supplied on **EVERY** canonical script invocation — this is the corrected contract that attempt 1 omitted.

- pre-mutation `docker compose` config resolved `127.0.0.1:14300:3000`;
- actual runtime binding after start = `127.0.0.1:14300->3000/tcp`;
- binding before reset = `127.0.0.1:14300->3000/tcp`;
- binding after reset = `127.0.0.1:14300->3000/tcp`.

The source contract already supports `JUICE_SHOP_HOST_PORT` via compose environment substitution. The first failure was an execution-harness omission, **not** a repository script bug — this record does not claim a repository script defect.

### Canonical image digest actually used

`bkimminich/juice-shop@sha256:e68144772ebaaca0ec117b38d44903af92416793230288ef7c5437fc4f26850a`

### Lifecycle results

The canonical lifecycle completed with exit code `0` at every step:

| Step | Result |
| --- | --- |
| `start.sh` | `PASS` |
| `status.sh` (1) | `PASS` |
| `smoke.sh` (1) | `PASS` |
| `reset.sh` | `PASS` |
| `status.sh` (2) | `PASS` |
| `smoke.sh` (2) | `PASS` |
| first `destroy.sh` | `PASS` |
| second `destroy.sh` | `PASS` — idempotence confirmed |

Health and both smokes `PASS`, reset `PASS`, destroy1 `PASS`, destroy2 idempotent `PASS`.

## Isolation and non-interference

The accepted run did not connect Kali and did not perform scanning, exploitation or external target traffic.

The Juice Shop lifecycle mutated **only** juice-shop-owned resources. Docker events/Compose ownership distinguish this from the rest of the host.

The run explicitly left the following unrelated resources unchanged by the Juice Shop lifecycle:

- unrelated Docker resources (not mutated by the lifecycle);
- Runner unchanged;
- Kali unchanged / disconnected;
- the canonical working tree NOT reset/stashed/cleaned.

No concurrent external activity was observed during the run window. Unrelated Docker resources were not mutated by the lifecycle. No signer, trust-store, Runner-promotion, policy, systemd, Gateway, Bridge, WebGoat or DVWA state was changed by the Juice Shop lifecycle.

## Final zero-residue proof

After the two canonical destroy operations:

- project-owned Juice Shop containers: `0`;
- project-owned Juice Shop volumes: `0`;
- project-owned Juice Shop networks: `0`;
- localhost high port `14300`: free again;
- Kali remained running and disconnected from `juice-shop-lab`;
- unrelated Docker resources preserved.

## Evidence manifest

The runtime produced eighteen sanitised local evidence files under `/tmp/hsl-issue394-juice-shop-evidence-attempt2/`. Their contents are intentionally not committed. A separate read-only run (`run_8fbe0ad257fb4252ad9797c9e913ad6b`) calculated file hashes and a deterministic aggregate manifest, proving `manifest.txt` 18/18 hashes OK.

**Manifest format:** `<sha256>  <size>  <relative-path>`, sorted deterministically by path.  
**Manifest SHA-256 (sha256sum of manifest.txt file contents):** `27e15027881a470a455b0c93388dcd9e765a36b1761929e8107a786a6592d307`

| Relative path | Bytes | SHA-256 |
| --- | ---: | --- |
| `00-compose-port-proof.txt` | 1487 | `d13631a7654aa104384a6cbe4f97beba7a20c5e7ddf5719a850f192dbfce4fba` |
| `01-start.log` | 1097 | `aeee02b152c79b5c9f6ed454e5b6b7a38f9a4882f5e507ed70641feae6cdd7ca` |
| `01b-binding-after-start.txt` | 248 | `ef91f64105d699ab8b58595715459cd1ac7cffcb202cd6f5601621e758a84e57` |
| `02-status1.log` | 773 | `4ee80e1f41fc5d5ac748bfd17ad970d54f0e8588ce8cea3cfd07c5dfe8934bb4` |
| `03-smoke1.log` | 813 | `ab8f3fc773b9cf53eff8260e7a440211449aacb28969c409aef0efa2598ad526` |
| `03b-binding-before-reset.txt` | 249 | `52a08c661bd689a749294098729e227a62dd818f565fb332b4d3def1de031218` |
| `04-reset.log` | 2189 | `aec5b840015f3355ef6e3202f28d6384545deb0e795a85aca78df7e156f10295` |
| `04b-binding-after-reset.txt` | 248 | `23702f4708f2f87df34d3731ffd4f53584721ef794e8df15685151052c7f925f` |
| `05-status2.log` | 773 | `13cb7e7e1a169462616b77e1afba0cba56e475effad39617c46f1e7f57449f3d` |
| `06-smoke2.log` | 813 | `fad4f7310173d81706326ed71867f3559a5824d3330d629e59f285f5b52c098d` |
| `07-destroy1.log` | 787 | `38eedc1d9fe8d45580fa18c25059a17a2a927ed668b09ea6e63cdeaf57d79310` |
| `08-destroy2.log` | 594 | `4923b4e4b7480bf01a34f7ca1d9812b24b1d3244a6abc54d1628ce1484b83c30` |
| `baseline.txt` | 3359 | `a0ac61c34c2eff410f368de1dc046730be4307d188ea2b3b8d25636e0601426b` |
| `final-proof.txt` | 372 | `41632d895e4140461c061beec973d022ed06246fda2ef4cbf23580efe80f800c` |
| `non-interference.txt` | 2956 | `d46e92045e9b894a0a45297e722a59baa56f0b75141ca24b5f40969c6b20a88d` |
| `runner.done` | 15 | `b37c98d5907a7ed2729ec071a4f87657f5c7da79a0ef15b25170238aa4007545` |
| `sequence-results.txt` | 293 | `cd50071e2997deb1553b4c860eebc81078c97b73ee86beb23c57135eb809ea2c` |
| `smoke-summary.txt` | 299 | `6512603e4ddfb14387661f0ca298fd7108cc437bfb7dd6fec7192475b00e4b8c` |

These hashes bind this audit record to the evidence set observed by the Hermes runtime. The `/tmp` files remain ephemeral local evidence and are not asserted to be durable/WORM custody. The custom aggregate `aggregate.sha256` value `f38d784e...` is NOT persisted as the manifest hash.

## Acceptance boundary

CHG-HSL-070 closes only the Juice Shop **live lifecycle/readiness/reset/zero-residue acceptance** for the revision tested above.

It does not change the governed Runner campaign `VAL-HSL-RUNNER-L1-LIVE-PROMOTION.yaml`, which remains `BLOCKED` / `HOLD` with `promotion_allowed=false`, candidate commit `a63ef01925e5c1b925936c1e73b11b2d6cd2a6a5` unchanged, and `VAL-HSL-RUNNER-L1-LIVE-PROMOTION` unaffected. Juice Shop acceptance is an independent lifecycle-evidence record; it grants no Runner, signer, trust-store, supplier-selection, assurance-profile, #53, or PROD/LAB_L1 promotion authority.

DVWA and WebGoat acceptances remain as previously recorded.
