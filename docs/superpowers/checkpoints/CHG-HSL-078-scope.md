# CHG-HSL-078 locked scope

The lane is restricted to repository-only authorization decision audit evidence: registration, lookup hit/miss/expiry and refusals. It must reuse the canonical AuditSink/EvidenceChain and must not enable runtime policies, install trust, select a provider, create sockets, or execute a target effect.
