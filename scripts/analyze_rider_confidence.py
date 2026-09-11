"""Diagnostic only: inspect trained-model ambiguity without changing the artifact."""
import json
import sys
from pathlib import Path

import joblib
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.ml.dataset_config import FAULT_FEATURES, MODEL_DIR, PROCESSED_DIR

metadata = json.loads((MODEL_DIR / 'fault_model_metadata.json').read_text())
cases = json.loads((PROCESSED_DIR / 'api_model_verification.json').read_text())
rider = next(r['verdict'] for r in cases if r['case'] == 'RIDER')
classes = metadata['classes']
confusion = metadata['confusion_matrix'][classes.index('RIDER')]
training = pd.read_csv(PROCESSED_DIR / 'fault_training_data.csv')
training = training[(training.split == 'train') & (training.scenario == 'RIDER')]
model = joblib.load(MODEL_DIR / 'fault_model.joblib')['pipeline']
frame = pd.DataFrame([rider['features']], columns=FAULT_FEATURES)
variants = {}
for distance in [0, 0.5, 1.5]:
    diagnostic = frame.copy()
    diagnostic['route_deviation_km'] = distance
    variants[str(distance)] = dict(zip(model.classes_, model.predict_proba(diagnostic)[0].tolist()))
report = {
    'original_features': rider['features'], 'original_probabilities': rider['class_probabilities'],
    'original_resolution': rider['outcome'],
    'held_out_rider_confusion': dict(zip(classes, confusion)),
    'rider_recall': metadata['classification_report']['RIDER']['recall'],
    'training_rider_route_deviation_quantiles_km': training.route_deviation_km.quantile([0, .25, .5, .75, 1]).to_dict(),
    'diagnostic_only_route_deviation_sensitivity': variants,
    'interpretation': 'The original case has a stationary stop but no route deviation. NEITHER is its main alternative. Training rider scenarios generally include both signals. These feature substitutions diagnose sensitivity only; no model, probability, or incident was modified.',
}
(PROCESSED_DIR / 'rider_confidence_analysis.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
