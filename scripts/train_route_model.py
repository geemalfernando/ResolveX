"""Generate GPS-route features and train an IsolationForest anomaly detector.

Normal rows look like a short last-mile hop. Anomalous rows have a long detour,
a long stationary stop, or a drop-off far from the customer address.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

FEATURES = [
    "detour_ratio",
    "max_stationary_minutes",
    "dropoff_distance_m",
    "total_distance_km",
    "straight_line_km",
    "avg_speed_kmh",
    "stop_count",
    "n_points",
]

DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "backend" / "app" / "ml" / "route_model.joblib"


def generate_dataset(n_rows: int = 3000, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows: list[dict[str, float]] = []

    for i in range(n_rows):
        anomalous = i >= int(n_rows * 0.82)
        straight = float(rng.uniform(1.2, 5.5))
        n_points = float(rng.integers(5, 16))

        if not anomalous:
            detour = float(rng.uniform(1.00, 1.45))
            stationary = float(rng.uniform(0.0, 6.0))
            dropoff = float(rng.uniform(0.0, 90.0))
            stops = float(rng.integers(0, 2))
            avg_speed = float(rng.uniform(12.0, 32.0))
        else:
            kind = int(rng.integers(0, 3))
            detour = float(rng.uniform(1.9, 3.4)) if kind != 2 else float(rng.uniform(1.1, 1.6))
            stationary = float(rng.uniform(12.0, 28.0)) if kind != 0 else float(rng.uniform(0.0, 7.0))
            dropoff = float(rng.uniform(220.0, 850.0)) if kind == 2 else float(rng.uniform(10.0, 120.0))
            stops = float(rng.integers(1, 4))
            avg_speed = float(rng.uniform(4.0, 14.0) if kind == 1 else rng.uniform(10.0, 22.0))

        rows.append(
            {
                "detour_ratio": detour,
                "max_stationary_minutes": stationary,
                "dropoff_distance_m": dropoff,
                "total_distance_km": straight * detour,
                "straight_line_km": straight,
                "avg_speed_kmh": avg_speed,
                "stop_count": stops,
                "n_points": n_points,
                "label": int(anomalous),
            }
        )

    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=3000)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    data = generate_dataset(args.rows)
    features = data[FEATURES]
    scaler = StandardScaler()
    scaled = scaler.fit_transform(features)

    isolation_forest = IsolationForest(
        n_estimators=250,
        contamination=0.18,
        random_state=7,
    )
    isolation_forest.fit(scaled)
    preds = isolation_forest.predict(scaled)
    predicted_anomaly = preds == -1
    actual = data["label"].to_numpy() == 1
    true_pos = int((predicted_anomaly & actual).sum())
    false_pos = int((predicted_anomaly & ~actual).sum())
    print(f"anomaly recall on synthetic labels: {true_pos / max(actual.sum(), 1):.3f}")
    print(f"false positives on normal rows: {false_pos}/{int((~actual).sum())}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "isolation_forest": isolation_forest,
            "scaler": scaler,
            "features": FEATURES,
        },
        args.output,
    )
    print(f"trained {len(data)} rows -> {args.output}")


if __name__ == "__main__":
    main()
