"""Run with python -m backend.app.ml.check_datasets before training."""
import hashlib

import pandas as pd

from .dataset_config import SOURCES


def inspect_datasets():
    metadata = {}
    missing = []
    for name, source in SOURCES.items():
        path = source["path"]
        print(f"{name}: {path} exists={path.is_file()}", flush=True)
        if not path.is_file():
            missing.append(str(path))
            continue
        frame = pd.read_csv(path)
        if source["target"] not in frame:
            raise ValueError(f"{name}: missing target {source['target']}")
        print(f"rows={len(frame)} columns={list(frame.columns)} target={source['target']}", flush=True)
        metadata[name] = {"rows": len(frame), "columns": list(frame.columns), "target": source["target"],
                          "url": source["url"], "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    if missing:
        raise FileNotFoundError("Both datasets are required before training. Missing: " + ", ".join(missing))
    return metadata


if __name__ == "__main__":
    inspect_datasets()
