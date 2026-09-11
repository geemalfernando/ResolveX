"""Generate a synthetic claim-history dataset and train IsolationForest + XGBoost.

Training deliberately includes mid-band / overlapping cases and label noise so
predict_proba is continuous (not only ~0 or ~1). A probability temperature is
saved with the bundle to soften overconfident scores at inference time.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import IsolationForest
from sklearn.metrics import classification_report, brier_score_loss
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

FEATURES = [
    "claims_last_90_days",
    "claims_last_30_days",
    "approved_ratio",
    "denied_ratio",
    "voucher_ratio",
    "reason_diversity",
    "avg_refund_amount",
    "max_refund_amount",
    "days_since_last_claim",
    "unique_reason_ratio",
]

DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "backend" / "app" / "ml" / "claim_history_model.joblib"
PROBABILITY_TEMPERATURE = 1.6
LABEL_NOISE_RATE = 0.08


def _row(
    claims_90: float,
    claims_30: float,
    approved_ratio: float,
    denied_ratio: float,
    voucher_ratio: float,
    reason_diversity: float,
    avg_amount: float,
    days_since: float,
    label: int,
    rng: np.random.Generator,
) -> dict[str, float]:
    # Keep ratios roughly valid
    total = approved_ratio + denied_ratio + voucher_ratio
    if total > 1.0 and total > 0:
        approved_ratio /= total
        denied_ratio /= total
        voucher_ratio /= total
    unique_reason_ratio = (reason_diversity / claims_90) if claims_90 else 0.0
    return {
        "claims_last_90_days": float(claims_90),
        "claims_last_30_days": float(claims_30),
        "approved_ratio": float(approved_ratio),
        "denied_ratio": float(denied_ratio),
        "voucher_ratio": float(voucher_ratio),
        "reason_diversity": float(reason_diversity),
        "avg_refund_amount": float(avg_amount),
        "max_refund_amount": float(avg_amount * rng.uniform(1.0, 1.5)) if avg_amount else 0.0,
        "days_since_last_claim": float(days_since),
        "unique_reason_ratio": float(unique_reason_ratio),
        "label": int(label),
    }


def generate_dataset(n_rows: int = 8000, seed: int = 7) -> pd.DataFrame:
    """Mix clean, mid-risk, and abuse rows so scores can land in the 30–70 band."""
    rng = np.random.default_rng(seed)
    rows: list[dict[str, float]] = []

    # Target mix: ~55% clean, ~25% mid/ambiguous, ~20% clear abuse
    n_clean = int(n_rows * 0.55)
    n_mid = int(n_rows * 0.25)
    n_abuse = n_rows - n_clean - n_mid

    for _ in range(n_clean):
        archetype = int(rng.integers(0, 4))
        if archetype == 0:
            rows.append(_row(0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 90.0, 0, rng))
        elif archetype == 1:
            claims_90 = int(rng.choice([1, 2], p=[0.65, 0.35]))
            approved = float(rng.uniform(0.0, 0.55))
            denied = float(rng.uniform(0.2, 1.0 - approved))
            voucher = max(0.0, 1.0 - approved - denied)
            rows.append(
                _row(
                    claims_90,
                    min(claims_90, int(rng.integers(0, claims_90 + 1))),
                    approved,
                    denied,
                    voucher,
                    float(min(claims_90, rng.integers(1, 3))),
                    float(rng.uniform(150, 600)),
                    float(rng.uniform(15, 85)),
                    0,
                    rng,
                )
            )
        elif archetype == 2:
            # Storm-week late cluster — legitimate
            claims_90 = int(rng.integers(2, 4))
            approved = float(rng.uniform(0.25, 0.65))
            denied = float(rng.uniform(0.2, 0.55))
            voucher = max(0.0, 1.0 - approved - denied)
            rows.append(
                _row(
                    claims_90,
                    claims_90,
                    approved,
                    denied,
                    voucher,
                    1.0,
                    float(rng.uniform(180, 480)),
                    float(rng.uniform(3, 25)),
                    0,
                    rng,
                )
            )
        else:
            claims_90 = 3
            approved = float(rng.uniform(0.25, 0.55))
            denied = float(rng.uniform(0.25, 0.5))
            voucher = max(0.0, 1.0 - approved - denied)
            rows.append(
                _row(
                    claims_90,
                    int(rng.integers(1, 3)),
                    approved,
                    denied,
                    voucher,
                    2.0,
                    float(rng.uniform(220, 650)),
                    float(rng.uniform(10, 45)),
                    0,
                    rng,
                )
            )

    for _ in range(n_mid):
        # Ambiguous band: sometimes labeled 0, sometimes 1 (overlap on purpose)
        archetype = int(rng.integers(0, 4))
        if archetype == 0:
            # 2–3 claims, mostly approved — soft risk
            claims_90 = int(rng.integers(2, 4))
            approved = float(rng.uniform(0.65, 0.9))
            denied = float(rng.uniform(0.0, 1.0 - approved))
            voucher = max(0.0, 1.0 - approved - denied)
            label = int(rng.random() < 0.35)
            rows.append(
                _row(
                    claims_90,
                    int(rng.integers(1, claims_90 + 1)),
                    approved,
                    denied,
                    voucher,
                    float(rng.integers(1, 3)),
                    float(rng.uniform(300, 850)),
                    float(rng.uniform(5, 30)),
                    label,
                    rng,
                )
            )
        elif archetype == 1:
            # 3–4 claims, mixed outcomes
            claims_90 = int(rng.integers(3, 5))
            approved = float(rng.uniform(0.45, 0.75))
            denied = float(rng.uniform(0.1, 0.4))
            voucher = max(0.0, 1.0 - approved - denied)
            label = int(rng.random() < 0.45)
            rows.append(
                _row(
                    claims_90,
                    int(rng.integers(2, claims_90 + 1)),
                    approved,
                    denied,
                    voucher,
                    float(rng.integers(2, 4)),
                    float(rng.uniform(350, 950)),
                    float(rng.uniform(3, 20)),
                    label,
                    rng,
                )
            )
        elif archetype == 2:
            # Mild voucher farming
            claims_90 = int(rng.integers(3, 5))
            label = int(rng.random() < 0.55)
            rows.append(
                _row(
                    claims_90,
                    int(rng.integers(2, claims_90 + 1)),
                    float(rng.uniform(0.1, 0.4)),
                    float(rng.uniform(0.0, 0.2)),
                    float(rng.uniform(0.5, 0.85)),
                    float(rng.integers(2, 4)),
                    float(rng.uniform(280, 700)),
                    float(rng.uniform(2, 18)),
                    label,
                    rng,
                )
            )
        else:
            # Elevated amount, few claims
            claims_90 = int(rng.integers(2, 4))
            approved = float(rng.uniform(0.7, 0.95))
            denied = max(0.0, 1.0 - approved - float(rng.uniform(0.0, 0.15)))
            voucher = max(0.0, 1.0 - approved - denied)
            label = int(rng.random() < 0.4)
            rows.append(
                _row(
                    claims_90,
                    min(claims_90, int(rng.integers(1, claims_90 + 1))),
                    approved,
                    denied,
                    voucher,
                    float(rng.integers(1, 3)),
                    float(rng.uniform(700, 1400)),
                    float(rng.uniform(4, 28)),
                    label,
                    rng,
                )
            )

    for _ in range(n_abuse):
        archetype = int(rng.integers(0, 5))
        if archetype == 0:
            claims_90 = int(rng.integers(4, 10))
            rows.append(
                _row(
                    claims_90,
                    int(rng.integers(2, claims_90 + 1)),
                    float(rng.uniform(0.88, 1.0)),
                    float(rng.uniform(0.0, 0.1)),
                    0.0,
                    float(rng.integers(3, 5)),
                    float(rng.uniform(450, 1200)),
                    float(rng.uniform(1, 10)),
                    1,
                    rng,
                )
            )
        elif archetype == 1:
            claims_90 = int(rng.integers(5, 12))
            rows.append(
                _row(
                    claims_90,
                    claims_90,
                    float(rng.uniform(0.8, 1.0)),
                    float(rng.uniform(0.0, 0.15)),
                    0.0,
                    float(rng.integers(2, 5)),
                    float(rng.uniform(500, 1400)),
                    float(rng.uniform(0, 5)),
                    1,
                    rng,
                )
            )
        elif archetype == 2:
            claims_90 = int(rng.integers(4, 8))
            rows.append(
                _row(
                    claims_90,
                    int(rng.integers(2, claims_90)),
                    float(rng.uniform(0.85, 1.0)),
                    0.0,
                    float(rng.uniform(0.0, 0.15)),
                    4.0,
                    float(rng.uniform(400, 1000)),
                    float(rng.uniform(1, 12)),
                    1,
                    rng,
                )
            )
        elif archetype == 3:
            claims_90 = int(rng.integers(3, 6))
            rows.append(
                _row(
                    claims_90,
                    int(rng.integers(2, claims_90 + 1)),
                    float(rng.uniform(0.85, 1.0)),
                    float(rng.uniform(0.0, 0.1)),
                    0.0,
                    float(rng.integers(2, 4)),
                    float(rng.uniform(900, 2200)),
                    float(rng.uniform(1, 15)),
                    1,
                    rng,
                )
            )
        else:
            claims_90 = int(rng.integers(4, 9))
            rows.append(
                _row(
                    claims_90,
                    int(rng.integers(2, claims_90 + 1)),
                    0.0,
                    0.0,
                    1.0,
                    float(rng.integers(2, 4)),
                    float(rng.uniform(300, 800)),
                    float(rng.uniform(1, 9)),
                    1,
                    rng,
                )
            )

    # Extra global label noise so the boundary is fuzzy
    for row in rows:
        if rng.random() < LABEL_NOISE_RATE:
            row["label"] = 1 - row["label"]

    rng.shuffle(rows)
    return pd.DataFrame(rows)


def _score_band_report(model, features: pd.DataFrame, labels: pd.Series, temperature: float) -> None:
    raw = model.predict_proba(features)[:, 1]
    # Apply same softening used at inference for the report
    softened = _soften(raw, temperature)
    bands = {
        "0-20": ((softened < 0.20).sum(), (labels[softened < 0.20] == 1).mean() if (softened < 0.20).any() else 0),
        "20-40": (((softened >= 0.20) & (softened < 0.40)).sum(), None),
        "40-60": (((softened >= 0.40) & (softened < 0.60)).sum(), None),
        "60-80": (((softened >= 0.60) & (softened < 0.80)).sum(), None),
        "80-100": ((softened >= 0.80).sum(), None),
    }
    print("softened probability band counts:")
    for name, (count, _) in bands.items():
        print(f"  {name}: {count}")
    print(f"brier (raw): {brier_score_loss(labels, raw):.4f}")
    print(f"brier (soft): {brier_score_loss(labels, softened):.4f}")


def _soften(probs: np.ndarray, temperature: float) -> np.ndarray:
    probs = np.clip(probs, 1e-6, 1 - 1e-6)
    logits = np.log(probs / (1 - probs))
    softened = 1 / (1 + np.exp(-logits / temperature))
    return softened


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=8000)
    parser.add_argument("--temperature", type=float, default=PROBABILITY_TEMPERATURE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    data = generate_dataset(args.rows)
    features = data[FEATURES]
    labels = data["label"]

    x_train, x_test, y_train, y_test = train_test_split(
        features, labels, test_size=0.2, random_state=7, stratify=labels
    )

    scaler = StandardScaler()
    x_train_scaled = scaler.fit_transform(x_train)

    isolation_forest = IsolationForest(
        n_estimators=200,
        contamination=0.12,
        random_state=7,
    )
    isolation_forest.fit(x_train_scaled[y_train.to_numpy() == 0])

    # Shallower / more regularized base learner + probability calibration
    base = XGBClassifier(
        n_estimators=120,
        max_depth=3,
        learning_rate=0.05,
        subsample=0.85,
        colsample_bytree=0.85,
        min_child_weight=4,
        reg_lambda=2.0,
        eval_metric="logloss",
        random_state=7,
    )
    xgboost = CalibratedClassifierCV(base, method="isotonic", cv=3)
    xgboost.fit(x_train, y_train)

    preds = xgboost.predict(x_test)
    print(classification_report(y_test, preds, digits=3))
    _score_band_report(xgboost, x_test, y_test, args.temperature)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "isolation_forest": isolation_forest,
            "xgboost": xgboost,
            "scaler": scaler,
            "features": FEATURES,
            "probability_temperature": args.temperature,
        },
        args.output,
    )
    print(f"trained {len(data)} rows (temp={args.temperature}) -> {args.output}")


if __name__ == "__main__":
    main()
