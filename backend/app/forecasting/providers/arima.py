"""ARIMA forecasting provider stub."""

from datetime import timedelta
from typing import List
from backend.app.forecasting.base import (
    ForecastProvider,
    ModelSpec,
    InferencePoint,
    PriceHistoryItem,
)


class ArimaProvider(ForecastProvider):
    """Autoregressive Integrated Moving Average (ARIMA) provider.

    Phase 1 architectural stub: computes forward projection with mean reversion
    and expanding variance envelopes without requiring heavy external runtimes.
    """

    @property
    def spec(self) -> ModelSpec:
        return ModelSpec(
            name="ARIMA",
            code="ARIMA",
            version="0.1.0-stub",
            description=(
                "Autoregressive Integrated Moving Average time-series model. "
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

        sorted_history = sorted(history, key=lambda x: x.trade_date)
        last_item = sorted_history[-1]
        last_price = last_item.close_price
        start_date = last_item.trade_date

        # 5-period simple average as mean reversion target
        window = sorted_history[-5:] if len(sorted_history) >= 5 else sorted_history
        mean_target = sum(item.close_price for item in window) / len(window)

        results: List[InferencePoint] = []
        current_date = start_date
        current_price = last_price

        for step in range(1, horizon_days + 1):
            current_date += timedelta(days=1)
            while current_date.weekday() >= 5:
                current_date += timedelta(days=1)

            # Gradual mean reversion
            current_price = max(
                0.01,
                round(current_price * 0.9 + mean_target * 0.1, 4),
            )
            # Expanding uncertainty bounds
            uncertainty = round(current_price * (0.018 * (step ** 0.5)), 4)

            results.append(
                InferencePoint(
                    target_date=current_date,
                    predicted_price=current_price,
                    lower_bound=max(0.01, round(current_price - uncertainty, 4)),
                    upper_bound=round(current_price + uncertainty, 4),
                    confidence_level=0.95,
                    is_demo=True,
                    notes=f"ARIMA architectural stub projection ({symbol})",
                )
            )

        return results
