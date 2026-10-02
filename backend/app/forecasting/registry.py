"""Registry for forecast inference providers."""

from typing import Dict, List, Optional
from backend.app.forecasting.base import ForecastProvider
from backend.app.forecasting.providers.lag_regression import LagInformedRegressionProvider
from backend.app.forecasting.providers.arima import ArimaProvider
from backend.app.forecasting.providers.lstm import LstmProvider


class ForecastRegistry:
    """Registry maintaining active forecast providers."""

    def __init__(self):
        self._providers: Dict[str, ForecastProvider] = {}
        # Register standard default providers
        self.register(LagInformedRegressionProvider())
        self.register(ArimaProvider())
        self.register(LstmProvider())

    def register(self, provider: ForecastProvider) -> None:
        """Register a forecasting provider instance."""
        self._providers[provider.spec.code] = provider

    def get(self, code: str) -> Optional[ForecastProvider]:
        """Retrieve provider by code."""
        return self._providers.get(code.upper())

    def list_all(self) -> List[ForecastProvider]:
        """Return list of all registered providers."""
        return list(self._providers.values())


# Global singleton registry
forecast_registry = ForecastRegistry()
