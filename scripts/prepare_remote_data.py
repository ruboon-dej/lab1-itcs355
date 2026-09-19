"""Upload the exact DVC-tracked raw dataset to BLOB_URI for Lab 2."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudlayer.factory import get_adapter
from src import config


def main() -> int:
    cfg = config.load()
    adapter = get_adapter(cfg)

    raw_path = cfg.raw_path

    if not raw_path.exists():
        raise SystemExit(
            f"{raw_path} does not exist. Run `dvc pull` first."
        )

    uri = adapter.upload(
        str(raw_path),
        "training-data/sensors.csv",
    )

    print(f"uploaded: {raw_path}")
    print(f"remote:   {uri}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())