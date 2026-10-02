"""Fresh all-data production refitting for Lag-Informed Regression."""

from collections.abc import Sequence
from dataclasses import dataclass
import logging

from backend.app.forecasting.real.config import DEFAULT_LAG_REGRESSION_CONFIG, LagRegressionConfig
from backend.app.forecasting.real.features.regression_features import (
    RegressionDataset,
    RegressionSample,
    feature_names_for_pacf_lags,
    regression_feature_contract,
)
from backend.app.forecasting.real.models.lag_regression import (
    LagRegressionFitMetadata,
    LagRegressionModel,
)
from backend.app.forecasting.real.training.cross_validation import select_pacf_lags

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LIRFittedModel:
    """A fitted estimator and its fold-appropriate PACF/parameter metadata."""

    model: LagRegressionModel
    pacf_selected_lags: tuple[int, ...]
    fit_metadata: LagRegressionFitMetadata

    def as_dict(self) -> dict[str, object]:
        return {
            "pacf_selected_lags": list(self.pacf_selected_lags),
            **self.fit_metadata.as_dict(),
        }


def _validate_candidate_contract(
    dataset: RegressionDataset,
    config: LagRegressionConfig,
) -> None:
    contract = regression_feature_contract(config.features)
    if dataset.feature_names != contract.candidate_feature_names:
        raise ValueError(
            "Regression dataset feature order does not match the configured "
            "candidate feature contract"
        )


def _validate_selected_fit_metadata(
    expected_feature_names: Sequence[str],
    metadata: LagRegressionFitMetadata,
) -> None:
    expected = tuple(expected_feature_names)
    if metadata.feature_names != expected:
        raise RuntimeError(
            "Persisted selected feature names differ from names passed to LASSO"
        )
    if not (
        len(metadata.scaler_mean)
        == len(metadata.scaler_scale)
        == len(metadata.scaler_variance)
        == len(expected)
    ):
        raise RuntimeError(
            "Scaler metadata does not align exactly with selected feature names"
        )


def _fit_with_local_pacf(
    dataset: RegressionDataset,
    samples: Sequence[RegressionSample],
    *,
    alpha: float,
    config: LagRegressionConfig,
) -> LIRFittedModel:
    chosen_samples = tuple(samples)
    training_returns = dataset.returns_through(chosen_samples[-1].target_date)
    pacf_lags = select_pacf_lags(
        training_returns,
        max_lag=config.pacf_max_lag,
        significance_z=config.pacf_significance_z,
    )
    feature_names = feature_names_for_pacf_lags(dataset.feature_names, pacf_lags)
    model = LagRegressionModel(
        alpha=alpha,
        max_iterations=config.max_iterations,
        tolerance=config.tolerance,
        coefficient_zero_tolerance=config.coefficient_zero_tolerance,
    ).fit(
        dataset.matrix(chosen_samples, feature_names=feature_names),
        dataset.targets(chosen_samples),
        feature_names,
    )
    metadata = model.metadata
    _validate_selected_fit_metadata(feature_names, metadata)
    return LIRFittedModel(
        model=model,
        pacf_selected_lags=pacf_lags,
        fit_metadata=metadata,
    )


def refit_lir_for_production(
    dataset: RegressionDataset,
    *,
    chosen_alpha: float,
    config: LagRegressionConfig = DEFAULT_LAG_REGRESSION_CONFIG,
) -> LIRFittedModel:
    """Fit a separate production estimator on all currently labeled samples."""
    _validate_candidate_contract(dataset, config)
    LOGGER.info(
        "Refitting LIR production model samples=%d alpha=%s",
        len(dataset.samples),
        chosen_alpha,
    )
    return _fit_with_local_pacf(
        dataset,
        dataset.samples,
        alpha=chosen_alpha,
        config=config,
    )
