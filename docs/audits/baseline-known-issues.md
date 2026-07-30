# Baseline known issues — 2026-07-30

These items were imported as-is from the operational baseline and
were **not fixed** in the import commit. They will be addressed in
separate branches and pull requests.

## 1. SKILL.md — MCP URL format

Update `skills/kali-mcp-lab/SKILL.md` so the URL is exclusively
`@url:\`http://127.0.0.1:5000\`` and bare `@url:` or
`@url:\`https://127.0.0.1:5000\`` are removed.

## 2. Juice Shop healthcheck depends on wget

The Juice Shop `compose.yaml` healthcheck uses `wget -q --spider`
but the official `bkimminich/juice-shop` image does not include
`wget`. Switch to `node -e`, `curl`, or `nc` instead.

## 3. WPScan writable state

`wpscan --version` fails with `/root/.wpscan` read-only filesystem.
Add a writable tmpfs or volume path before classifying FUNCTIONAL-PASS.

## 4. Gobuster MCP execution validation

`gobuster_scan` is binary-present but not FUNCTIONAL-PASS against a
stable local target. Add a reachable target or resolve the DNS issue
inside the Kali container.

## 5. Dirb MCP execution validation

`dirb_scan` is binary-present but not FUNCTIONAL-PASS against a
stable local target. Requires the same fix as #4.

## 6. SQLMap synthetic SQLi target

No synthetic SQLi endpoint was available during the baseline audit.
Add a local SQLi target and re-run.

## 7. Hydra synthetic authentication target

No synthetic authentication service was available during the baseline
audit. Add a disposable service and valid credentials, then re-run.

## 8. John the Ripper synthetic hash

The John test wrote to `/root/.john` on a tmpfs that did not persist.
Confirm writable home or cache path before re-testing.

## 9. Enum4linux disposable Samba target

No disposable Samba target exists in the lab topology. Add one and
re-run the scan.

## 10. Metasploit writable state

`msfconsole` logs `/root is not writable`. Add a writable tmpfs or
volume for `/root/.msf4` or a custom home path.

## 11. Juice Shop end-to-end workflow

The full lifecycle (start → smoke → scan → stop → destroy) has not
been executed end-to-end yet in the new repository.

## 12. Deployment drift detection

`drift-check.sh` and `deploy.sh` are present but not integrated with
a running `.deployment.json` comparison against the live Hermes host.
