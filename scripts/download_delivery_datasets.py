"""Download the two requested public CSVs to stable repository-relative paths."""
from pathlib import Path
import io
import sys
import urllib.request
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.ml.dataset_config import KAGGLE_PATH, ZOMATO_PATH


def fetch(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def main():
    if not ZOMATO_PATH.exists():
        ZOMATO_PATH.parent.mkdir(parents=True, exist_ok=True)
        ZOMATO_PATH.write_bytes(fetch("https://raw.githubusercontent.com/Parth-Malik/Zomato-Delivery-Time-Prediction/main/Zomato%20Dataset.csv"))
    if not KAGGLE_PATH.exists():
        KAGGLE_PATH.parent.mkdir(parents=True, exist_ok=True)
        archive = fetch("https://www.kaggle.com/api/v1/datasets/download/dharmendrapandit12/food-delivery-time-prediction-dataset")
        with zipfile.ZipFile(io.BytesIO(archive)) as files:
            name = next(n for n in files.namelist() if Path(n).name == KAGGLE_PATH.name)
            KAGGLE_PATH.write_bytes(files.read(name))
    from backend.app.ml.check_datasets import inspect_datasets
    inspect_datasets()


if __name__ == "__main__":
    main()
