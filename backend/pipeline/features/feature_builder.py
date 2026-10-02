"""Feature engineering scaffold for lightweight PSE price forecasting.

Calculates multi-period lags and moving averages using pure Python
to maintain negligible memory consumption on ~1 GiB RAM host.
"""

from typing import List, Dict, Any


class FeatureBuilder:
    """Builds lag and rolling features from ordered historical prices."""

    @staticmethod
    def extract_lag_features(prices: List[float], lags: List[int] = [1, 2, 5]) -> Dict[str, float]:
        """Extract historical price lags relative to latest observation."""
        if not prices:
            return {}

        features: Dict[str, float] = {}
        last_price = prices[-1]

        for lag in lags:
            if len(prices) > lag:
                lag_val = prices[-(lag + 1)]
                features[f"lag_{lag}"] = lag_val
                features[f"return_lag_{lag}"] = round((last_price - lag_val) / lag_val, 6)
            else:
                features[f"lag_{lag}"] = last_price
                features[f"return_lag_{lag}"] = 0.0

        # Simple moving average
        window_5 = prices[-5:] if len(prices) >= 5 else prices
        features["ma_5"] = round(sum(window_5) / len(window_5), 4)

        return features
