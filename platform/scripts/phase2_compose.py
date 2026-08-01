from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
import yaml

ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "platform" / "phase2" / "environments.yaml"
RUNTIME_CONTEXT = "../../../platform/runtime/phase2-safe-lab"


def load_catalog() -> dict:
    data = yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 1:
        raise SystemExit("unsupported Phase 2 catalog")
    return data


def get_env(data: dict, env_id: str) -> dict:
    matches = [item for item in data["environments"] if item["id"] == env_id]
    if len(matches) != 1:
        raise SystemExit(f"expected one catalog entry for {env_id}, found {len(matches)}")
    return matches[0]


def port_var(env_id: str) -> str:
    return env_id.upper().replace("-", "_") + "_HOST_PORT"


def render(env: dict, runtime: dict) -> dict:
    commit = str(env["source_commit"])
    suffix = re.sub(r"[^A-Za-z0-9]", "", commit)[:12].lower() or "synthetic"
    tag = f"source-{suffix}" if env.get("source_repo") else commit
    env_id = env["id"]
    internal = f"{env_id}-internal"
    publication = f"{env_id}-publication"
    r = env["resources"]
    marker = env_id.upper().replace("-", "_") + "_SYNTHETIC_MARKER"
    return {
        "name": env_id,
        "services": {
            "target": {
                "build": {
                    "context": RUNTIME_CONTEXT,
                    "args": {
                        "LAB_ID": env_id,
                        "LAB_MODE": env["mode"],
                        "SOURCE_REPO": env.get("source_repo", ""),
                        "SOURCE_COMMIT": commit,
                        "SOURCE_ARCHIVE_SHA256": "",
                    },
                },
                "image": f"hermes-local/{env_id}:{tag}",
                "environment": {
                    "LAB_ID": env_id,
                    "LAB_MODE": env["mode"],
                    "SOURCE_REPO": env.get("source_repo", ""),
                    "SOURCE_COMMIT": commit,
                    "HERMES_PHASE2_SYNTHETIC_MARKER": marker,
                },
                "networks": [internal],
                "expose": ["8080", "8090"],
                "security_opt": ["no-new-privileges:true"],
                "cap_drop": ["ALL"],
                "read_only": True,
                "tmpfs": ["/tmp", "/run"],
                "deploy": {
                    "resources": {
                        "limits": {
                            "cpus": str(r["cpus"]),
                            "memory": r["memory_limit"],
                            "pids": int(r["pids"]),
                        },
                        "reservations": {"memory": r["memory_reservation"]},
                    }
                },
                "healthcheck": {
                    "test": [
                        "CMD",
                        "python",
                        "-c",
                        "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3).read(1)",
                    ],
                    "interval": "10s",
                    "timeout": "5s",
                    "retries": 12,
                    "start_period": "10s",
                },
            },
            "proxy": {
                "image": runtime["publication_proxy"],
                "depends_on": {"target": {"condition": "service_healthy"}},
                "ports": [
                    "127.0.0.1:${"
                    + port_var(env_id)
                    + ":-"
                    + str(env["host_port"])
                    + "}:8080"
                ],
                "networks": [internal, publication],
                "security_opt": ["no-new-privileges:true"],
                "cap_drop": ["ALL"],
                "read_only": True,
                "tmpfs": ["/tmp", "/run"],
                "command": ["TCP-LISTEN:8080,reuseaddr,fork", "TCP:target:8080"],
                "deploy": {
                    "resources": {
                        "limits": {"cpus": "0.25", "memory": "128m", "pids": 64},
                        "reservations": {"memory": "64m"},
                    }
                },
                "healthcheck": {
                    "test": [
                        "CMD-SHELL",
                        "exec socat -T3 -u OPEN:/dev/null TCP:127.0.0.1:8080,connect-timeout=3 >/dev/null 2>&1",
                    ],
                    "interval": "10s",
                    "timeout": "5s",
                    "retries": 12,
                    "start_period": "5s",
                },
            },
        },
        "networks": {
            internal: {"name": internal, "driver": "bridge", "internal": True},
            publication: {"name": publication, "driver": "bridge"},
        },
    }


def self_test() -> None:
    data = load_catalog()
    if not data.get("environments"):
        raise SystemExit("Phase 2 catalog has no environments")
    document = render(data["environments"][0], data["runtime"])
    proxy = document["services"]["proxy"]
    test = proxy["healthcheck"]["test"]
    if test[0] != "CMD-SHELL" or "socat" not in test[1] or "wget" in test[1]:
        raise SystemExit("proxy healthcheck must use the image-native socat binary")
    if proxy["command"][0] == "socat":
        raise SystemExit("proxy command must not duplicate the image ENTRYPOINT")
    internal = data["environments"][0]["id"] + "-internal"
    if document["networks"][internal].get("internal") is not True:
        raise SystemExit("target network must remain internal")
    print("PHASE2_COMPOSE_SELF_TEST_OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("environment", nargs="?")
    parser.add_argument("--output")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.environment:
        parser.error("environment is required unless --self-test is used")
    data = load_catalog()
    env = get_env(data, args.environment)
    document = yaml.safe_dump(render(env, data["runtime"]), sort_keys=False, width=120)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(document, encoding="utf-8")
    else:
        sys.stdout.write(document)


if __name__ == "__main__":
    main()
