"""Pipeline forecasting runner module."""

from typing import List, Dict, Any
from backend.app.forecasting.base import (
    PriceHistoryItem,
    InferencePoint,
)
from backend.app.forecasting.registry import forecast_registry


class PipelineForecastRunner:
    """Orchestrates model inference across registered providers."""

    def __init__(self):
        self.registry = forecast_registry

    def run_inference_for_symbol(
        self,
        symbol: str,
        history: List[PriceHistoryItem],
        model_codes: List[str] = ["LAG_REGRESSION", "ARIMA", "LSTM"],
        horizon_days: int = 5,
    ) -> Dict[str, List[InferencePoint]]:
        """Run inference for all specified model codes."""
        results: Dict[str, List[InferencePoint]] = {}

        for code in model_codes:
            provider = self.registry.get(code)
            if provider:
                results[code] = provider.generate_forecast(
                    symbol=symbol,
                    history=history,
                    horizon_days=horizon_days,
                )

        return results
