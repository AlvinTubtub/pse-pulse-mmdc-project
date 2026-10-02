"""LSTM forecasting provider stub."""

from datetime import timedelta
import math
from typing import List
from backend.app.forecasting.base import (
    ForecastProvider,
    ModelSpec,
    InferencePoint,
    PriceHistoryItem,
)


class LstmProvider(ForecastProvider):
    """Long Short-Term Memory (LSTM) Recurrent Neural Network provider.

    Phase 1 architectural stub: models multi-step sequential dynamics without
    requiring PyTorch or TensorFlow runtimes on the ~1 GiB RAM host VM.
    """

    @property
    def spec(self) -> ModelSpec:
        return ModelSpec(
            name="LSTM",
            code="LSTM",
            version="0.1.0-stub",
            description=(
                "Deep learning recurrent network for sequential market dependency modeling. "
                "Phase 1 architectural inference stub (zero deep-learning runtime overhead)."
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

        results: List[InferencePoint] = []
        current_date = start_date
        current_price = last_price

        for step in range(1, horizon_days + 1):
            current_date += timedelta(days=1)
            while current_date.weekday() >= 5:
                current_date += timedelta(days=1)

            # Simulated smooth sequential non-linear projection
            delta = math.sin(step * 0.5) * (last_price * 0.005)
            current_price = max(0.01, round(last_price + delta, 4))
            spread = round(current_price * (0.02 * math.sqrt(step)), 4)

            results.append(
                InferencePoint(
                    target_date=current_date,
                    predicted_price=current_price,
                    lower_bound=max(0.01, round(current_price - spread, 4)),
                    upper_bound=round(current_price + spread, 4),
                    confidence_level=0.95,
                    is_demo=True,
                    notes=f"LSTM architectural stub projection ({symbol})",
                )
            )

        return results
