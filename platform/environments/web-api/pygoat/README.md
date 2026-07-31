# PyGoat Lab

## Source and runtime

- Canonical repository: `adeyosemanputra/pygoat`
- Source commit: `19d17cc8874861142b330636d068bbde54e86b85`
- Runtime image: `ghcr.io/pestoura/hermes-pygoat@sha256:3df04f28225c1b9a7a888edbb724540364c3d88967578fc688d47632272069a9`
- Application manifest (`linux/amd64`): `sha256:b18537e75b823bdb08b5f9da95551f6072c24d5d25f2517b26f7fb7d504c4496`
- Attestation manifest (`unknown/unknown`): `sha256:5e1f6826db789d7bc60ef7be0dfd7a2220c7e7adf0276b057623c8534dfb4473`
- Declared base: `python:3.10-slim-bookworm`
- Build recipe: `pygoat-python310-compat-v2`

The application image is published by the controlled GHCR workflow with SBOM and BuildKit provenance. Runtime consumption uses the accepted immutable OCI index digest, never a mutable tag or the attestation manifest. The rejected v1 index `sha256:20616206188704f51cb1123083722531e13a84c19ac65ff721dfb8691acfe8da` is retained only as historical evidence and must not be used at runtime.

The accepted v2 recipe preserves the immutable upstream application and challenge source, Python 3.10 compatibility wrapper, `psycopg2-binary==2.9.9`, transitive `psycopg2==2.9.12`, `PyYAML==6.0.2`, Django 4.2, Gunicorn 23.0.0 and the SQLite database model. It prevents django-heroku from replacing the authorised Django host list, which is restricted to `pygoat.herokuapp.com`, `0.0.0.0`, `127.0.0.1`, `localhost` and `pygoat`.

## Targets

- Host: `http://127.0.0.1:${PYGOAT_HOST_PORT:-8000}/`
- Kali: `http://pygoat:8000/`

Only loopback is published. Runtime egress is declared as permitted.

## Lifecycle and evidence

Use the eight executable lifecycle scripts under `scripts/`. Start pulls missing images and does not build application source on the Hermes host. Reset destroys container state and recreates it from the accepted immutable image. Destroy disconnects Kali, removes project resources, preserves images and supports a second execution.

Acceptance is limited to connectivity and bounded safe scanning. Do not perform exploitation, brute force, destructive actions, denial of service, external targets or LAN targets.

Store sanitised evidence in `.runtime/evidence/pygoat/`.
