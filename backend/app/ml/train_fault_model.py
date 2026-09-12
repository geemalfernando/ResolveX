"""Train an ideathon classifier on controlled, explicitly synthetic fault labels."""
import json
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, log_loss
from sklearn.pipeline import Pipeline

from .check_datasets import inspect_datasets
from .dataset_config import ETA_FEATURES, FAULT_FEATURES, LABEL_PROVENANCE, MODEL_DIR, PROCESSED_DIR

CLASSES = ["MERCHANT", "RIDER", "EXTERNAL", "NEITHER"]


def augment(data, eta):
    rng = np.random.default_rng(23)
    # Bounded, reproducible sample from each partition/source; source split is preserved.
    sampled = pd.concat([g.sample(n=min(3000, len(g)), random_state=23) for _, g in data.groupby(["source_dataset", "split"])], ignore_index=True)
    expected = eta.predict(sampled[ETA_FEATURES])
    rows = []
    for i, row in sampled.iterrows():
        distance = row.distance_km if pd.notna(row.distance_km) else 5
        prep = row.prep_time_min if pd.notna(row.prep_time_min) else 15
        residual = abs(row.delivery_time_min - expected[i])
        severity = np.clip(12 + residual + distance * 0.35 + rng.normal(0, 4), 8, 65)
        for scenario in CLASSES:
            features = dict(
                prep_delay_min=rng.normal(0, 2.5), pickup_delay_min=max(0, rng.normal(2, 1.5)),
                travel_delay_min=rng.normal(0, 3), route_deviation_km=max(0, rng.normal(0.12, 0.15)),
                stationary_time_min=max(0, rng.normal(2, 1.5)), zone_late_percentage=rng.uniform(0, 18),
                zone_average_delay_min=rng.uniform(0, 3),
            )
            if scenario == "MERCHANT":
                features["prep_delay_min"] += severity + prep * 0.25
                features["pickup_delay_min"] += rng.uniform(0, 4)
            elif scenario == "RIDER":
                features["travel_delay_min"] += severity + rng.uniform(2, 18)
                features["stationary_time_min"] += rng.uniform(8, 28)
                features["route_deviation_km"] += rng.uniform(0.2, 3) + distance * 0.04
            elif scenario == "EXTERNAL":
                adverse = row.traffic in ("high", "jam") or row.weather in ("rain", "storm", "fog")
                features["travel_delay_min"] += severity
                features["zone_late_percentage"] = rng.uniform(35 if adverse else 25, 98)
                features["zone_average_delay_min"] += severity * rng.uniform(0.6, 1.1)
                features["stationary_time_min"] += rng.uniform(0, 10)
            # Mixed evidence + label noise make scenario boundaries imperfect.
            if rng.random() < 0.15:
                features[rng.choice(["prep_delay_min", "travel_delay_min", "stationary_time_min"])] += rng.uniform(5, 20)
            label = scenario if rng.random() >= 0.07 else rng.choice([c for c in CLASSES if c != scenario])
            # Match incomplete live observations; don't encode unknown as observed zero.
            for feature in ["prep_delay_min", "pickup_delay_min", "travel_delay_min", "route_deviation_km", "stationary_time_min", "zone_average_delay_min"]:
                if rng.random() < 0.08:
                    features[feature] = np.nan
            rows.append(dict(features, source_dataset=row.source_dataset, source_row_id=row.source_row_id,
                             split=row.split, scenario=scenario, fault_party=label, expected_delivery_time_min=expected[i],
                             source_delivery_time_min=row.delivery_time_min, label_origin="synthetic_scenario"))
    return pd.DataFrame(rows)


def main():
    inspect_datasets()
    data = pd.read_csv(PROCESSED_DIR / "combined_delivery_data.csv")
    eta = joblib.load(MODEL_DIR / "eta_model.joblib")["pipeline"]
    scenarios = augment(data, eta)
    scenarios.to_csv(PROCESSED_DIR / "fault_training_data.csv", index=False)
    train, test = scenarios[scenarios.split == "train"], scenarios[scenarios.split == "test"]
    assert not set(zip(train.source_dataset, train.source_row_id)) & set(zip(test.source_dataset, test.source_row_id))
    pipeline = Pipeline([("imputer", SimpleImputer(strategy="median", add_indicator=True)),
                         ("model", RandomForestClassifier(n_estimators=150, min_samples_leaf=12, max_depth=12, n_jobs=-1, random_state=23))])
    pipeline.fit(train[FAULT_FEATURES], train.fault_party)
    pred = pipeline.predict(test[FAULT_FEATURES])
    probs = pipeline.predict_proba(test[FAULT_FEATURES])
    metadata = {
        "model_name": "fault_classifier", "model_version": "2.0-synthetic", "label_provenance": LABEL_PROVENANCE,
        "trained_at": datetime.now(timezone.utc).isoformat(), "sklearn_version": sklearn.__version__,
        "features": FAULT_FEATURES, "classes": list(pipeline.classes_),
        "train_rows": len(train), "test_rows": len(test), "source_counts": scenarios.groupby("source_dataset").size().to_dict(),
        "sources": json.loads((PROCESSED_DIR / "dataset_manifest.json").read_text()),
        "scenario_generation": {"seed": 23, "label_noise": 0.07, "mixed_evidence_rate": 0.15, "missing_observation_rate": 0.08,
                                "split": "Source rows split before augmentation; all variants of a source row stay together"},
        "train_accuracy": accuracy_score(train.fault_party, pipeline.predict(train[FAULT_FEATURES])),
        "test_accuracy": accuracy_score(test.fault_party, pred), "test_log_loss": log_loss(test.fault_party, probs, labels=pipeline.classes_),
        "classification_report": classification_report(test.fault_party, pred, output_dict=True),
        "confusion_matrix": confusion_matrix(test.fault_party, pred, labels=pipeline.classes_).tolist(),
        "test_accuracy_by_source": {source: accuracy_score(g.fault_party, pipeline.predict(g[FAULT_FEATURES])) for source, g in test.groupby("source_dataset")},
        "limitations": "Measures reproduction of simulated scenarios, not real-world fault accuracy. Probabilities are not calibrated on adjudicated incidents. Refund history and photo do not determine fault classes.",
    }
    joblib.dump(dict(pipeline=pipeline, **metadata), MODEL_DIR / "fault_model.joblib", compress=3)
    (MODEL_DIR / "fault_model_metadata.json").write_text(json.dumps(metadata, indent=2))
    print(json.dumps({k: metadata[k] for k in ["train_rows", "test_rows", "test_accuracy", "test_log_loss", "test_accuracy_by_source"]}, indent=2))


if __name__ == "__main__":
    main()
