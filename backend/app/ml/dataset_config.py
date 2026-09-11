"""Repository-relative paths shared by acquisition, training and inference."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
ZOMATO_PATH = DATA_DIR / "external/zomato/Zomato Dataset.csv"
KAGGLE_PATH = DATA_DIR / "external/synthetic_food_delivery/Food_Delivery_Time_Prediction.csv"
PROCESSED_DIR = DATA_DIR / "processed"
MODEL_DIR = Path(__file__).resolve().parent
SOURCES = {
    "zomato": {"path": ZOMATO_PATH, "target": "Time_taken (min)", "url": "https://github.com/Parth-Malik/Zomato-Delivery-Time-Prediction"},
    "kaggle_synthetic": {"path": KAGGLE_PATH, "target": "Time_taken_min", "url": "https://www.kaggle.com/datasets/dharmendrapandit12/food-delivery-time-prediction-dataset"},
}
ETA_FEATURES = ["distance_km", "prep_time_min", "order_hour", "is_weekend", "weather", "traffic", "vehicle"]
FAULT_FEATURES = ["prep_delay_min", "pickup_delay_min", "travel_delay_min", "route_deviation_km", "stationary_time_min", "zone_late_percentage", "zone_average_delay_min"]
LABEL_PROVENANCE = "Synthetic/pseudo-labelled incident scenarios derived from public/synthetic delivery datasets; not genuine historical fault determinations."
