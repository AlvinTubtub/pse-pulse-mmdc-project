"""Lag-Informed Regression forecasting provider stub."""

from datetime import timedelta
from typing import List
from backend.app.forecasting.base import (
    ForecastProvider,
    ModelSpec,
    InferencePoint,
    PriceHistoryItem,
)


class LagInformedRegressionProvider(ForecastProvider):
    """Lag-Informed Regression provider.

    Phase 1 architectural stub: computes forward projection using lag-window
    momentum and moving average without heavy machine learning training dependencies.
    """

    @property
    def spec(self) -> ModelSpec:
        return ModelSpec(
            name="Lag-Informed Regression",
            code="LAG_REGRESSION",
            version="0.1.0-stub",
            description=(
                "Linear regression model utilizing multi-period price lags and moving averages. "
                "Phase 1 architectural inference stub."
            ),
            is_stub=True,
        )

    def generate_forecast(
        self,
        symbol: str,
        history: List[PriceHistoryItem],
        horizon_days: int = 5,
    ) -> List[InferencePoint]:
        if not history:
            return []

        # Sort history by trade_date ascending
        sorted_history = sorted(history, key=lambda x: x.trade_date)
        last_item = sorted_history[-1]
        last_price = last_item.close_price
        start_date = last_item.trade_date

        # Compute simple lag slope if history has >= 2 points
        slope = 0.0
        if len(sorted_history) >= 2:
            prev_price = sorted_history[-2].close_price
            slope = (last_price - prev_price) * 0.2  # conservative damped momentum

        results: List[InferencePoint] = []
        current_date = start_date
        current_price = last_price

        for step in range(1, horizon_days + 1):
            # Advance to next weekday (skip Saturday & Sunday)
            current_date += timedelta(days=1)
            while current_date.weekday() >= 5:
                current_date += timedelta(days=1)

            # Dampened projection
            current_price = max(0.01, round(current_price + (slope / (1 + step * 0.1)), 4))
            spread = round(current_price * (0.015 * step), 4)

            results.append(
                InferencePoint(
                    target_date=current_date,
                    predicted_price=current_price,
                    lower_bound=max(0.01, round(current_price - spread, 4)),
                    upper_bound=round(current_price + spread, 4),
                    confidence_level=0.95,
                    is_demo=True,
                    notes=f"Lag-regression architectural stub projection ({symbol})",
                )
            )

        return results
