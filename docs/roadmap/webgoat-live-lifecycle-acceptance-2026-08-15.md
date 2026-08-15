# WebGoat/WebWolf live lifecycle acceptance — 2026-08-15

**Change:** `CHG-HSL-064`  
**Accepted runtime run:** `run_f3ecec54f9464366aa1edfb32ac58b33`  
**Evidence-manifest run:** `run_57c6a33bad4a42ea97780d5c17b8644a`  
**Repository revision exercised:** `dd3677b6fb531c72ec7c5ea6fb5f82da94a27f37`  
**Scope:** local OWASP WebGoat/WebWolf lifecycle only  
**Disposition:** `PASS / ACCEPTED-LIVE-LIFECYCLE`

This record persists the sanitised acceptance result for the post-fix WebGoat/WebWolf lifecycle. It does **not** authorize Runner promotion, signer/trust activation, Kali target traffic, exploitation or any other lab.

## Historical run retained as UNKNOWN

The earlier post-fix run `run_73cd8ef359ff486f93faeb7c2dc46290` remains `UNKNOWN`. The Hermes bridge exposes no recoverable checkpoints for it, so it is not reclassified as PASS or FAIL. CHG-HSL-064 obtains fresh evidence instead of inferring a result from that historical run.

## First 2026-08-15 preflight attempt

Run `run_80e379dc5b6c4364a4f0bfec6d8750df` stopped before mutation because the conservative preflight found:

- a non-owned container `eager_solomon` using the same pinned WebGoat image but without the canonical Compose project ownership label;
- unrelated services already owning localhost ports `8080` and `9090`;
- a canonical repository working tree containing unrelated work and not at the exact current `origin/main` revision.

No lifecycle script or Docker mutation was executed in that run. The canonical WebGoat project already had zero owned containers, volumes and networks.

The blockers were resolved without touching unrelated resources: the accepted run used an exact temporary `git archive` export of `origin/main` and the documented host-port override capability.

## Accepted execution

The accepted run required `origin/main` to equal:

`dd3677b6fb531c72ec7c5ea6fb5f82da94a27f37`

A clean temporary export of that exact revision was used. The existing canonical working tree was not checked out, reset, stashed, cleaned or edited.

Host-port overrides were:

- `WEBGOAT_HOST_PORT=18080`
- `WEBWOLF_HOST_PORT=19090`

Both ports were verified free on `127.0.0.1` before mutation. Container-internal service ports remained `8080` and `9090`.

The canonical lifecycle completed with exit code `0` at every step:

| Step | Result |
| --- | --- |
| `start.sh` | `PASS` |
| `status.sh` | `PASS` |
| `smoke.sh` | `PASS` |
| `reset.sh` | `PASS` |
| second `status.sh` | `PASS` |
| second `smoke.sh` | `PASS` |
| first `destroy.sh` | `PASS` |
| second `destroy.sh` | `PASS` — idempotence confirmed |

The smoke checks observed WebGoat and WebWolf successfully through their localhost-only publications, matched the pinned image digest and retained the expected project network semantics.

## Isolation and non-interference

The accepted run did not connect Kali and did not perform scanning, exploitation or external target traffic.

The pre-existing non-owned WebGoat-image container `eager_solomon` was deliberately preserved. Unrelated services using ports `8080` and `9090` were also preserved. The lifecycle ran only on the alternate localhost ports above.

The run explicitly left the following unrelated resources unchanged:

- `eager_solomon`;
- `m365-ui-mcp-control-plane-1`;
- `monitoring-prometheus-1`;
- `hermes-kali-mcp`.

No signer, trust-store, Runner-promotion, policy, systemd, Gateway, Bridge, DVWA or Juice Shop state was changed.

## Final zero-residue proof

After the two canonical destroy operations:

- project-owned WebGoat containers: `0`;
- project-owned WebGoat volumes: `0`;
- project-owned WebGoat networks: `0`;
- localhost port `18080`: free again;
- localhost port `19090`: free again;
- Kali remained running and disconnected from `webgoat-lab`;
- the pinned WebGoat image was preserved.

The temporary exact-revision export was removed after the run.

## Evidence manifest

The runtime produced ten sanitised local evidence files under `/tmp/wg-evidence/`. Their contents are intentionally not committed. A separate read-only run calculated file hashes and a deterministic aggregate manifest.

**Manifest format:** `<sha256>  <size>  <relative-path>\n`, sorted deterministically by path.  
**Manifest SHA-256:** `0530018208cbcded9498dcf9afa96be26cf5ce1893f2f1f90caa626a5028e323`

| Relative path | Bytes | SHA-256 |
| --- | ---: | --- |
| `01-start.log` | 1572 | `62d74972e44a025e8ea35353046bec7c10fb08981fbb8bc5dbd03e8dccbdb8e0` |
| `02-status1.log` | 1149 | `dda6ea97b99e9f4b0f1eb753dcf2d21b1fae0623ea3f1cc151121a55eac65fac` |
| `03-smoke1.log` | 1275 | `0546600a0a3b28cc757d870ca32168e792292976dbe4f9e2613cf43db1abc64c` |
| `04-reset.log` | 2696 | `134fcea2e743d219c8becf5b3a21719f093d22ab99ef285c2bdb7a819f555fec` |
| `05-status2.log` | 1173 | `392ff5bbf26dc521651ff89e229365530e5bf53b79fd5dae087073f95074f81f` |
| `06-smoke2.log` | 1299 | `9f9e65d86f705ef2ab94d35288bc7e9ee86be62f9c78e5ed5576b97fbe817afa` |
| `07-destroy1.log` | 980 | `6d02f20de4ad66d0bc89e67b5e5f3aafd6a9769dae765ae71560d7cf1106e3da` |
| `08-destroy2.log` | 518 | `2deb80a53ad1d19360ad859089327f2a9303875fdaf4aa3ee2e271f68f1db88a` |
| `baseline.txt` | 297 | `6863ab8d0dd21c52469990bdd00d7b4b7f8930b5a04e61d39457b26cd26a1e67` |
| `final-proof.txt` | 765 | `fe94fb04b593bbc8e50e12be2d0293853c32fbb3737e43dca8e2fc031065381c` |

These hashes bind this audit record to the evidence set observed by the Hermes runtime. The `/tmp` files remain ephemeral local evidence and are not asserted to be durable/WORM custody.

## Acceptance boundary

CHG-HSL-064 closes only the WebGoat/WebWolf **live lifecycle/readiness/reset/zero-residue acceptance** for the revision tested above.

It does not change the governed Runner campaign, which remains fail-closed until its separate unresolved live prerequisites are observed. DVWA and Juice Shop live lifecycle acceptance also remain independent pending work.
