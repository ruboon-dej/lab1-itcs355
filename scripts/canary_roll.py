"""Canary deploy + rollback helper for Lab 3."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# Make the repository root importable when this script is run directly.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

STATE_FILE = Path(__file__).resolve().parent.parent / "reports" / "canary_state.json"


def _load_env() -> None:
    env_file = Path(__file__).resolve().parent.parent / "cloud.env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


def _az(*args, check: bool = True) -> str:
    result = subprocess.run(
        ["az", *args],
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"az {' '.join(args)} failed: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def _get_endpoint_name() -> str:
    project_id = os.environ.get("PROJECT_ID", "")
    return os.environ.get("ENDPOINT_NAME", f"itcs355-{project_id}-predict")


def _get_latest_revision(endpoint: str) -> str:
    rg = os.environ["AZURE_RESOURCE_GROUP"]
    return _az(
        "containerapp", "show",
        "--name", endpoint,
        "--resource-group", rg,
        "--query", "properties.latestRevisionName",
        "--output", "tsv",
    )


def _get_traffic(endpoint: str) -> dict:
    rg = os.environ["AZURE_RESOURCE_GROUP"]
    raw = _az(
        "containerapp", "show",
        "--name", endpoint,
        "--resource-group", rg,
        "--query", "properties.configuration.ingress.revisionWeights",
        "--output", "json",
    )
    import json as _json
    weights = _json.loads(raw)
    result = {}
    if isinstance(weights, list):
        for item in weights:
            name = item.get("name", item.get("revisionName", ""))
            wt = item.get("weight", 0)
            if name:
                result[name] = wt
    elif isinstance(weights, dict):
        result = weights
    return result


def _set_traffic(endpoint: str, traffic: dict[str, int]) -> None:
    from cloudlayer.factory import get_adapter
    from src.config import load

    cfg = load()
    adapter = get_adapter(cfg)
    adapter.set_traffic(endpoint, traffic)


def _save_state(prod_revision: str, canary_revision: str) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({
        "prod_revision": prod_revision,
        "canary_revision": canary_revision,
    }, indent=2))


def _load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    return json.loads(STATE_FILE.read_text())


def cmd_canary(args: argparse.Namespace) -> None:
    _load_env()
    endpoint = _get_endpoint_name()
    registry = os.environ.get("CONTAINER_REGISTRY", "").rstrip("/")
    model_version = str(args.version)

    prod_revision = _get_latest_revision(endpoint)
    print(f"Production revision: {prod_revision}")

    from cloudlayer.factory import get_adapter
    from src.config import load

    cfg = load()
    adapter = get_adapter(cfg)

    os.environ["SERVE_IMAGE_TAG"] = args.tag if args.tag else os.environ.get("SERVE_IMAGE_TAG", "latest")
    model_ref = f"{registry}:{model_version}" if registry else f"{cfg.model_registry_name}:{model_version}"

    print(f"Deploying canary: {model_ref}")
    adapter.deploy_canary(model_ref, endpoint, "Standard_DS2_v2")

    canary_revision = _get_latest_revision(endpoint)
    print(f"Canary revision: {canary_revision}")

    if canary_revision == prod_revision:
        print("WARNING: canary revision same as production revision")
    else:
        traffic = {prod_revision: 90, canary_revision: 10}
        _set_traffic(endpoint, traffic)
        print(f"Traffic set: {prod_revision}=90, {canary_revision}=10")

    _save_state(prod_revision, canary_revision)
    print("Done.")


def cmd_rollback(args: argparse.Namespace) -> None:
    _load_env()
    endpoint = _get_endpoint_name()

    state = _load_state()
    prod_revision = state.get("prod_revision")

    if not prod_revision:
        traffic = _get_traffic(endpoint)
        if not traffic:
            prod_revision = _get_latest_revision(endpoint)
        else:
            prod_revision = max(traffic, key=lambda r: traffic[r])
        print(f"No state file; defaulting to: {prod_revision}")

    traffic = {prod_revision: 100}
    _set_traffic(endpoint, traffic)
    print(f"Traffic set: {prod_revision}=100")
    print("Rollback done.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Canary deploy + rollback for Lab 3")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_canary = sub.add_parser("canary", help="Deploy canary and shift traffic")
    p_canary.add_argument("--version", type=str, default="3")
    p_canary.add_argument("--tag", type=str, default=None)
    p_canary.set_defaults(func=cmd_canary)

    p_rollback = sub.add_parser("rollback", help="Roll back traffic to production")
    p_rollback.set_defaults(func=cmd_rollback)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
