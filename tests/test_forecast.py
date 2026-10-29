import unittest

import numpy as np
import pandas as pd

from forecast import fit_and_forecast


class ForecastTests(unittest.TestCase):
    def test_zero_revenue_holdout_has_no_mape(self):
        monthly = pd.DataFrame({
            "month": pd.period_range("2019-01", periods=48, freq="M").astype(str),
            "revenue": [100.0] * 36 + [0.0] * 12,
        })

        result = fit_and_forecast(monthly)

        self.assertIsNotNone(result)
        self.assertIsNone(result["mape"])
        self.assertIsNone(result["baseline_mape"])
        self.assertTrue(np.isfinite(result["forecast"]["revenue"]).all())

    def test_positive_revenue_holdout_returns_finite_scores(self):
        monthly = pd.DataFrame({
            "month": pd.period_range("2019-01", periods=48, freq="M").astype(str),
            "revenue": [100.0] * 48,
        })

        result = fit_and_forecast(monthly)

        self.assertIsNotNone(result)
        self.assertTrue(np.isfinite(result["mape"]))
        self.assertTrue(np.isfinite(result["baseline_mape"]))
        self.assertEqual(len(result["forecast"]), 6)


if __name__ == "__main__":
    unittest.main()
