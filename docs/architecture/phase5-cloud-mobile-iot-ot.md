# Phase 5 — Cloud, mobile, firmware and IoT/OT runtime preparation

## Scope

This delivery prepares manifests, drivers, classifications and admission constraints. It creates no AWS, Azure or GCP resource, installs no emulator on the Hermes host, imports no firmware image and activates no external hardware.

The canonical admission matrix is `platform/domain-preparation/phase5-policy.yaml`.

## Classification matrix

| Domain | Classification | Driver model | Activation in this phase |
| --- | --- | --- | --- |
| LocalStack / Azurite | `CURRENT-LIMITED` | local Docker emulation | no |
| AWS/Azure/GCP sandbox labs | `CLOUD-SANDBOX` | Terraform + provider-specific sandbox driver | no |
| Android/emulated mobile | `FUTURE-HARDWARE` | Android Emulator / ADB / MobSF sidecar | no |
| Firmware analysis | `FUTURE-HARDWARE` | QEMU + isolated analysis sidecar | no |
| MQTT/Modbus/ICS simulation | `FUTURE-HARDWARE` | protocol simulators | no |
| Zigbee/USB/physical OT | `EXTERNAL-HARDWARE` | explicit hardware boundary | no |

## Cloud sandbox contract

A real cloud sandbox can only move from prepared to active after all of the following are externally supplied and verified:

- dedicated non-production account/subscription/project;
- ephemeral least-privilege credentials;
- explicit cost budget and alerts;
- hard TTL and deterministic destroy path;
- ownership and campaign tags;
- allowlisted regions/services;
- Human-in-the-Loop approval.

None of those preconditions is synthesized by this repository. Their absence is a deny decision, not a reason to fall back to personal or production credentials.

## Mobile and firmware contract

Mobile and firmware artefacts remain outside Git. Device/emulator state is treated as ephemeral evidence-bearing runtime state. A future driver must own create/start/status/reset/destroy, isolated networking and data cleanup. MobSF or equivalent analysis services are sidecars; they do not grant device execution authority.

## IoT/OT contract

Protocol simulation is separated from physical hardware. Simulators must remain inside dedicated lab networks with no route to production control systems. Any USB, Zigbee or external OT interface is `EXTERNAL-HARDWARE`, default-disabled and requires explicit human approval plus inventory/ownership evidence before attachment.

## Issue #12 completion boundary

Issue #12 is complete when the domain/driver matrix and admission constraints validate in CI. Real cloud resource creation, emulator installation and hardware activation are expressly outside the issue and remain future separately authorized work.
