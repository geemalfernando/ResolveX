"""Normalize operational records without inventing source fault labels."""
import json

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from .check_datasets import inspect_datasets
from .dataset_config import ETA_FEATURES, KAGGLE_PATH, PROCESSED_DIR, ZOMATO_PATH


def normalize_category(series, mapping=None):
    result = series.astype("string").str.strip().str.lower().replace({"nan": pd.NA, "": pd.NA})
    if mapping:
        result = result.replace(mapping)
    return result.fillna("unknown")


def normalize_sources():
    zomato = pd.read_csv(ZOMATO_PATH)
    kaggle = pd.read_csv(KAGGLE_PATH)
    order = pd.to_datetime(zomato.Time_Orderd, format="%H:%M", errors="coerce")
    pickup = pd.to_datetime(zomato.Time_Order_picked, format="%H:%M", errors="coerce")
    prep = ((pickup - order).dt.total_seconds() / 60) % 1440
    lat1, lon1, lat2, lon2 = [pd.to_numeric(zomato[c], errors="coerce").abs() for c in
        ["Restaurant_latitude", "Restaurant_longitude", "Delivery_location_latitude", "Delivery_location_longitude"]]
    valid_coords = lat1.between(1, 90) & lat2.between(1, 90) & lon1.between(1, 180) & lon2.between(1, 180)
    a, b, c, d = map(np.radians, [lat1, lon1, lat2, lon2])
    distance = 6371 * 2 * np.arcsin(np.sqrt(np.clip(np.sin((c-a)/2)**2 + np.cos(a)*np.cos(c)*np.sin((d-b)/2)**2, 0, 1)))
    z = pd.DataFrame({
        "source_dataset": "zomato", "source_row_id": zomato.ID.astype(str),
        "distance_km": distance.where(valid_coords & (distance <= 50)),
        "distance_basis": "straight_line", "prep_time_min": prep.where(prep <= 120),
        "prep_basis": "order_to_pickup_proxy", "order_hour": order.dt.hour,
        "is_weekend": pd.to_datetime(zomato.Order_Date, format="%d-%m-%Y", errors="coerce").dt.dayofweek.ge(5).astype(int),
        "weather": normalize_category(zomato.Weather_conditions, {"sunny": "clear", "stormy": "storm", "sandstorms": "storm", "windy": "wind"}),
        "traffic": normalize_category(zomato.Road_traffic_density),
        "vehicle": normalize_category(zomato.Type_of_vehicle, {"electric_scooter": "electric scooter"}),
        "delivery_time_min": pd.to_numeric(zomato["Time_taken (min)"].astype(str).str.replace(r"[^\d.]", "", regex=True), errors="coerce"),
    })
    k = pd.DataFrame({
        "source_dataset": "kaggle_synthetic", "source_row_id": kaggle.Order_ID.astype(str),
        "distance_km": pd.to_numeric(kaggle.Road_Distance_km, errors="coerce"),
        "distance_basis": "road", "prep_time_min": pd.to_numeric(kaggle.Preparation_Time_Min, errors="coerce"),
        "prep_basis": "preparation", "order_hour": kaggle.Order_Hour,
        "is_weekend": kaggle.Is_Weekend,
        "weather": normalize_category(kaggle.Weather),
        "traffic": normalize_category(kaggle.Traffic_Level, {"moderate": "medium", "heavy": "high"}),
        "vehicle": normalize_category(kaggle.Vehicle_Type, {"bike": "motorcycle"}),
        "delivery_time_min": pd.to_numeric(kaggle.Time_taken_min, errors="coerce"),
    })
    combined = pd.concat([z, k], ignore_index=True)
    combined = combined.loc[combined.delivery_time_min.between(1, 240)].copy()
    combined = combined.drop_duplicates(["source_dataset", "source_row_id"]).reset_index(drop=True)
    # Split source rows once. All scenarios from one row stay in the same partition.
    train, test = train_test_split(combined.index, test_size=0.2, random_state=17, stratify=combined.source_dataset)
    combined["split"] = "train"
    combined.loc[test, "split"] = "test"
    return combined


def main():
    metadata = inspect_datasets()
    combined = normalize_sources()
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    combined.to_csv(PROCESSED_DIR / "combined_delivery_data.csv", index=False)
    metadata["normalization"] = {
        "distance": "Zomato straight-line vs Kaggle road distance: retained as imperfect proxies; basis recorded; metrics reported by source.",
        "preparation": "Zomato order-to-pickup proxy vs Kaggle prep duration; prep_basis recorded.",
        "split": "80/20 stratified by source, seed 17, before fitting or incident augmentation",
        "retained_rows": combined.groupby("source_dataset").size().to_dict(),
        "eta_features": ETA_FEATURES,
    }
    (PROCESSED_DIR / "dataset_manifest.json").write_text(json.dumps(metadata, indent=2))
    print(f"Saved {len(combined)} operational rows")


if __name__ == "__main__":
    main()
