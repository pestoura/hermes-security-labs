# Phase 4 — VM, infrastructure, network and Active Directory labs

## Delivery boundary

This phase defines the architecture and resource constraints for laboratories that must not be represented as ordinary application containers. It does not install Proxmox, libvirt, EVE-NG or GNS3 and does not provision Windows or Active Directory workloads on the Hermes host.

## Runtime drivers

| Driver | Intended use | Current authority |
| --- | --- | --- |
| `libvirt` | Local KVM/QEMU pilot when host capability is explicitly approved | read-only discovery only |
| `proxmox` | Preferred future dedicated bare-metal or second-host virtualization plane | design only |
| `external-hypervisor` | Existing externally managed virtualization platform | design only; explicit operator approval required |

The repository remains the configuration source of truth. Observed hypervisor state is non-authoritative and must never be automatically reconciled into Git.

## Resource budgets

| Lab class | vCPU | RAM | Disk | Concurrency | Status |
| --- | ---: | ---: | ---: | ---: | --- |
| Metasploitable Linux pilot | 2 | 2 GiB | 24 GiB | 1 | `FUTURE-VM` |
| Windows server/workstation pair | 4 | 8 GiB | 120 GiB | 1 | `FUTURE-VM` |
| GOAD Mini | 6 | 12 GiB | 180 GiB | 1 | `FUTURE-VM` |
| GOAD Light/Full/SCCM | 12+ | 32+ GiB | 400+ GiB | 0 on current Hermes host | `FUTURE-HARDWARE` |
| EVE-NG/GNS3 topology | workload dependent | 16+ GiB | 120+ GiB | 0 on current Hermes host | `FUTURE-HARDWARE` |

A budget is an admission limit, not an allocation request. A lab is refused if host observation cannot prove enough free resources without affecting Hermes control-plane services.

## Isolation requirements

- one virtual network namespace or hypervisor network per lab/campaign;
- no bridged LAN exposure by default;
- outbound egress denied by default and enabled only by an explicit approved profile;
- lab management interfaces are not exposed to workloads;
- snapshots and rollback references are mandatory before intrusive L3/L4 exercises;
- credentials are synthetic or dedicated lab credentials only and are never committed to Git;
- evidence exported from a VM is sanitized before repository or customer-visible persistence;
- at most one heavy VM/AD lab may be admitted on the current hardware profile.

## Lifecycle contract

Future drivers must implement `create`, `start`, `status`, `stop`, `reset` and `destroy` with idempotent cleanup. Reset must restore a named clean snapshot and destroy must prove absence of project-owned VM, disk, network and temporary metadata residue before the lab can be reused.

The current `virtual-machine` runtime remains `CURRENT-LIMITED`: repository manifests and read-only host discovery are permitted, while provisioning, snapshot manipulation, rollback and deletion remain unavailable until a separately approved runtime integration is validated.

## Migration sequence

1. Keep the current Hermes host unchanged and perform only read-only KVM/libvirt capability discovery.
2. Use the Metasploitable Linux pilot as the first VM lifecycle candidate because it has the smallest resource footprint.
3. Validate lifecycle, isolated networking, snapshot/reset and zero-residue cleanup on a non-production virtualization plane.
4. Introduce GOAD Mini only after the VM pilot is stable and resource admission is enforced.
5. Move GOAD Light/Full/SCCM and network emulation to Proxmox bare metal or a second dedicated host; they are not admitted on the current Hermes hardware baseline.
6. Keep `external-hypervisor` behind explicit operator approval and a dedicated trust boundary; no generic remote command surface is introduced.

## Completion statement for issue #11

The issue is complete at the **design and manifest boundary** when this architecture, resource budgets and the associated future-state manifests validate in CI. It does not claim a deployed VM runtime or an operational Active Directory laboratory.
