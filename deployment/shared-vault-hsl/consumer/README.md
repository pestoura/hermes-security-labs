# Hardened Secret Zero consumer

This directory defines the ephemeral operator shell used for future HSL shared-Vault Secret Zero and signer-evidence windows.

The image is deliberately separate from the long-lived provider probe. It copies only the pinned Vault CLI into a runtime image that does not inherit the official Vault image `VOLUME` declarations.

## Security boundary

The consumer:

- runs as UID/GID `10001:10001`;
- has a read-only root filesystem;
- drops all Linux capabilities;
- uses `no-new-privileges`;
- is never privileged;
- mounts only the public Vault CA volume, read-only;
- has only an ephemeral `/tmp` tmpfs;
- shares the probe network namespace so its source IPv4 remains the freshly observed probe `/32`;
- receives no RoleID, SecretID, wrapping token or Vault token through Compose/environment configuration.

The image contains no `/vault/file` or `/vault/logs` volumes. Secret material may exist only transiently in the operator-controlled shell memory during the HITL procedure.

## Operator boundary

Creating a SecretID, creating/copying a wrapping token, unwrap, RoleID handling and AppRole authentication remain operator-only HITL actions. Do not automate them and do not paste their values into GitHub, logs, evidence or ChatGPT.
