from dataclasses import dataclass
import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from xgboost import XGBClassifier

@dataclass
class PredictionMetrics:
    auc: float | None
    brier: float
    samples: int

class BaselinePredictor:
    def __init__(self, feature_columns: list[str]):
        self.feature_columns = feature_columns
        self.model = XGBClassifier(
            n_estimators=250, max_depth=4, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            objective="binary:logistic", eval_metric="logloss", random_state=42
        )
        self.calibrator: IsotonicRegression | None = None

    def fit(self, x_train, y_train):
        self.model.fit(x_train[self.feature_columns], y_train)
        return self

    def fit_calibration(self, x_validation, y_validation):
        raw = self.model.predict_proba(x_validation[self.feature_columns])[:, 1]
        self.calibrator = IsotonicRegression(out_of_bounds="clip")
        self.calibrator.fit(raw, y_validation)
        return self

    def predict_probability(self, x):
        raw = self.model.predict_proba(x[self.feature_columns])[:, 1]
        return raw if self.calibrator is None else self.calibrator.predict(raw)

    def evaluate(self, x_test, y_test) -> PredictionMetrics:
        p = self.predict_probability(x_test)
        auc = float(roc_auc_score(y_test, p)) if len(set(y_test)) == 2 else None
        return PredictionMetrics(auc=auc, brier=float(brier_score_loss(y_test, p)), samples=len(y_test))
