# Observability, failure assurance and maturity M0–M5

Repository-owned contract candidate for `SVP2-D-02`.

## Implemented guarantees

- executable steps fail closed unless fresh readiness evidence is `ready`;
- readiness evidence has a bounded TTL;
- the canonical failure suite contains restart, invalid JSON, empty stdout, timeout, network loss, disk full, partial cleanup, concurrency, cancellation and incompatible version cases;
- maturity is derived only from explicit evidence and cannot skip missing gates;
- M2 requires the complete passing failure suite;
- M3 introduces golden labs, golden findings and reproducibility;
- M4 adds false-positive/false-negative evidence and cleanup score;
- M5 additionally requires production observation and retirement readiness;
- advertised operations cannot be no-ops and must require effect evidence;
- OpenTelemetry/W3C trace attributes preserve campaign/run/step/attempt correlation.

## Deliberate non-claims

OpenTelemetry export, real readiness probes, chaos execution and production maturity assessment remain `NOT_RUN`. This block validates the contract and promotion logic only and performs no runtime or fault injection.

`NO_RUNTIME_CHANGE`.
