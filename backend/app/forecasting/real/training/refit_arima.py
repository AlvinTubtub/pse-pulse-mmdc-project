"""Fresh all-data production refitting for ARIMA."""

from collections.abc import Sequence
from dataclasses import dataclass
import logging

from backend.app.forecasting.real.config import ArimaConfig, DEFAULT_ARIMA_CONFIG
from backend.app.forecasting.real.domain import OhlcvRecord, require_chronological_records
from backend.app.forecasting.real.models.arima import (
    ArimaSpecification,
    FittedArimaModel,
    fit_arima,
)

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ArimaProductionFit:
    """A fitted production ARIMA model and its diagnostic metadata."""

    model: FittedArimaModel
    fit_metadata: dict[str, object]


def refit_arima_for_production(
    records: Sequence[OhlcvRecord],
    *,
    selected_specification: ArimaSpecification,
    config: ArimaConfig = DEFAULT_ARIMA_CONFIG,
) -> ArimaProductionFit:
    """Fit the selected configuration once using all available Close values."""
    require_chronological_records(records)
    close_values = tuple(record.close for record in records)
    LOGGER.info(
        "Refitting ARIMA production model observations=%d order=%s trend=%s",
        len(close_values),
        selected_specification.order,
        selected_specification.trend,
    )
    fitted = fit_arima(close_values, selected_specification, config=config)
    return ArimaProductionFit(
        model=fitted,
        fit_metadata=fitted.fit_metadata(),
    )
