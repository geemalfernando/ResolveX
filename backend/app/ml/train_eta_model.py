"""Train/evaluate ETA against both sources, fitting transforms on training rows only."""
import json
from datetime import datetime, timezone

import joblib
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from .check_datasets import inspect_datasets
from .dataset_config import ETA_FEATURES, MODEL_DIR, PROCESSED_DIR


def metrics(y, prediction):
    return {"mae_min": mean_absolute_error(y, prediction), "rmse_min": mean_squared_error(y, prediction) ** 0.5, "r2": r2_score(y, prediction)}


def main():
    inspect_datasets()
    data = pd.read_csv(PROCESSED_DIR / "combined_delivery_data.csv")
    train, test = data[data.split == "train"], data[data.split == "test"]
    preprocessor = ColumnTransformer([
        ("numeric", SimpleImputer(strategy="median", add_indicator=True), ETA_FEATURES[:4]),
        ("categorical", Pipeline([("impute", SimpleImputer(strategy="most_frequent")), ("encode", OneHotEncoder(handle_unknown="ignore"))]), ETA_FEATURES[4:]),
    ])
    pipeline = Pipeline([("preprocessor", preprocessor), ("model", RandomForestRegressor(n_estimators=100, max_depth=16, min_samples_leaf=8, n_jobs=-1, random_state=17))])
    pipeline.fit(train[ETA_FEATURES], train.delivery_time_min)
    metadata = {
        "model_name": "delivery_eta", "model_version": "2.0", "trained_at": datetime.now(timezone.utc).isoformat(),
        "sklearn_version": sklearn.__version__, "features": ETA_FEATURES,
        "target": "delivery_time_min", "train_rows": len(train), "test_rows": len(test),
        "sources": json.loads((PROCESSED_DIR / "dataset_manifest.json").read_text()),
        "train_metrics": metrics(train.delivery_time_min, pipeline.predict(train[ETA_FEATURES])),
        "test_metrics": metrics(test.delivery_time_min, pipeline.predict(test[ETA_FEATURES])),
        "test_metrics_by_source": {source: metrics(group.delivery_time_min, pipeline.predict(group[ETA_FEATURES])) for source, group in test.groupby("source_dataset")},
        "baseline_test_mae_min": mean_absolute_error(test.delivery_time_min, [train.delivery_time_min.median()] * len(test)),
        "limitations": "Mixed straight-line/road distances and pickup/prep proxies; live weather is unavailable. Evaluate on live operations before production use.",
    }
    joblib.dump(dict(pipeline=pipeline, **metadata), MODEL_DIR / "eta_model.joblib", compress=3)
    (MODEL_DIR / "eta_model_metadata.json").write_text(json.dumps(metadata, indent=2))
    print(json.dumps(metadata["test_metrics_by_source"], indent=2), flush=True)


if __name__ == "__main__":
    main()
