"""Monthly revenue forecast: linear trend + month-of-year seasonality."""
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression


def _features(t: np.ndarray, months: np.ndarray) -> np.ndarray:
    return np.column_stack([t, np.eye(12)[months - 1]])


def fit_and_forecast(monthly: pd.DataFrame, horizon: int = 6):
    """monthly: columns [month 'YYYY-MM', revenue]. Returns dict or None if too short."""
    s = monthly.set_index(pd.PeriodIndex(monthly["month"], freq="M"))["revenue"]
    s = s.reindex(pd.period_range(s.index.min(), s.index.max(), freq="M"), fill_value=0.0)
    if len(s) < 24:
        return None
    t = np.arange(len(s))
    months = s.index.month.to_numpy()
    y = s.to_numpy(dtype=float)
    X = _features(t, months)

    # Hold out the last 12 months to check the model honestly
    split = len(s) - 12
    model = LinearRegression().fit(X[:split], y[:split])
    pred = model.predict(X[split:])
    nz = y[split:] > 0
    mape = float(np.mean(np.abs(pred[nz] - y[split:][nz]) / y[split:][nz]) * 100)
    base = np.full(12, y[:split].mean())
    base_mape = float(np.mean(np.abs(base[nz] - y[split:][nz]) / y[split:][nz]) * 100)

    # Refit on everything, then forecast
    final = LinearRegression().fit(X, y)
    ft = np.arange(len(s), len(s) + horizon)
    fidx = pd.period_range(s.index[-1] + 1, periods=horizon, freq="M")
    fc = np.clip(final.predict(_features(ft, fidx.month.to_numpy())), 0, None)

    return {
        "history": pd.DataFrame({"month": s.index.astype(str), "revenue": y}),
        "forecast": pd.DataFrame({"month": fidx.astype(str), "revenue": fc}),
        "holdout": pd.DataFrame({"month": s.index[split:].astype(str),
                                 "actual": y[split:], "predicted": pred}),
        "mape": mape, "baseline_mape": base_mape,
    }
