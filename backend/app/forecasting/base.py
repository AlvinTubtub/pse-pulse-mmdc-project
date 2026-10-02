"""Forecasting Provider base abstraction.

Defines the pluggable inference interface for PSE Pulse models.
All providers in Phase 1 are lightweight inference stubs designed to run
within the ~1 GiB RAM target without requiring heavy training runtimes
such as TensorFlow or PyTorch.
"""

from abc import ABC, abstractmethod
from datetime import date
from typing import List, Optional
from pydantic import BaseModel, Field


class ModelSpec(BaseModel):
    name: str
    code: str
    version: str
    description: str
    is_stub: bool = True


class InferencePoint(BaseModel):
    target_date: date
    predicted_price: float
    lower_bound: Optional[float] = None
    upper_bound: Optional[float] = None
    confidence_level: float = 0.95
    is_demo: bool = True
    notes: Optional[str] = None


class PriceHistoryItem(BaseModel):
    trade_date: date
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: int


class ForecastProvider(ABC):
    """Abstract base class for all forecasting inference providers."""

    @property
    @abstractmethod
    def spec(self) -> ModelSpec:
        """Return provider metadata specification."""
        pass

    @abstractmethod
    def generate_forecast(
        self,
        symbol: str,
        history: List[PriceHistoryItem],
        horizon_days: int = 5,
    ) -> List[InferencePoint]:
        """Generate forward predictions for the given asset symbol.

        Must NOT trigger model training. Inference only.
        """
        pass
