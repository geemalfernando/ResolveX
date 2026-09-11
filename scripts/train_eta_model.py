"""Train ResolveX's local ETA model from the referenced Zomato dataset.

The model is deliberately limited to operational ETA features that can also be
constructed from a ResolveX case. It makes no network/API calls at inference time.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

DATA_URL = "https://raw.githubusercontent.com/Parth-Malik/Zomato-Delivery-Time-Prediction/main/Zomato%20Dataset.csv"
FEATURES = [
    "distance_km", "prep_time_min", "order_hour", "pickup_hour",
    "order_day_of_week", "is_weekend", "is_peak_hour", "multiple_deliveries",
    "weather", "traffic", "vehicle",
]
NUMERIC = FEATURES[:8]
CATEGORICAL = FEATURES[8:]


def haversine_km(lat1, lon1, lat2, lon2):
    import numpy as np

    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


def prepare(data: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    data = data.copy()
    order_time = pd.to_datetime(data["Time_Orderd"], format="%H:%M", errors="coerce")
    pickup_time = pd.to_datetime(data["Time_Order_picked"], format="%H:%M", errors="coerce")
    prep = (pickup_time.dt.hour * 60 + pickup_time.dt.minute) - (order_time.dt.hour * 60 + order_time.dt.minute)
    prep = prep.where(prep >= 0, prep + 1440).clip(upper=120)
    data["distance_km"] = haversine_km(
        data["Restaurant_latitude"].abs(), data["Restaurant_longitude"].abs(),
        data["Delivery_location_latitude"].abs(), data["Delivery_location_longitude"].abs(),
    ).clip(upper=30)
    data["prep_time_min"] = prep
    data["order_hour"] = order_time.dt.hour
    data["pickup_hour"] = pickup_time.dt.hour
    data["order_day_of_week"] = pd.to_datetime(data["Order_Date"], format="%d-%m-%Y", errors="coerce").dt.dayofweek
    data["is_weekend"] = (data["order_day_of_week"] >= 5).astype(int)
    data["is_peak_hour"] = data["order_hour"].isin([12, 13, 14, 19, 20, 21, 22]).astype(int)
    data["multiple_deliveries"] = pd.to_numeric(data["multiple_deliveries"], errors="coerce")
    data["weather"] = data["Weather_conditions"]
    data["traffic"] = data["Road_traffic_density"]
    data["vehicle"] = data["Type_of_vehicle"]
    target = pd.to_numeric(data["Time_taken (min)"], errors="coerce")
    features = data[FEATURES].replace({"NaN ": None, "NaN": None})
    valid = target.notna() & features["order_hour"].notna() & features["pickup_hour"].notna()
    return features.loc[valid], target.loc[valid]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--output", type=Path, default=Path("backend/app/ml/eta_model.joblib"))
    args = parser.parse_args()
    data = pd.read_csv(args.dataset or DATA_URL)
    features, target = prepare(data)
    numeric = Pipeline([("imputer", SimpleImputer(strategy="median"))])
    categorical = Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("onehot", OneHotEncoder(handle_unknown="ignore"))])
    preprocessor = ColumnTransformer([("numeric", numeric, NUMERIC), ("categorical", categorical, CATEGORICAL)])
    pipeline = Pipeline([("preprocessor", preprocessor), ("model", RandomForestRegressor(n_estimators=250, max_depth=18, min_samples_leaf=3, n_jobs=-1, random_state=7))])
    pipeline.fit(features, target)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"pipeline": pipeline, "features": FEATURES, "source": DATA_URL}, args.output)
    print(f"trained {len(features)} rows -> {args.output}")


if __name__ == "__main__":
    main()