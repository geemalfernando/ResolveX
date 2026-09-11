"""Compatibility entry point: train ETA from the prepared local datasets."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.ml.train_eta_model import main

if __name__ == "__main__":
    main()
