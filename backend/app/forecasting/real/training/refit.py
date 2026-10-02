"""Offline training and artifact generation CLI for PSE Pulse.

Refits production-grade Lag-Informed Regression (LIR/LASSO) and ARIMA models
against historical OHLCV data, calculates cryptographic SHA-256 checksums,
and outputs versioned model artifact bundles with companion JSON metadata.
"""

import argparse
from datetime import date
import logging
from pathlib import Path
import sys
from typing import List, Optional, Sequence

from backend.app.database import SessionLocal
from backend.app.forecasting.real.artifacts.writer import persist_model_artifact
from backend.app.forecasting.real.config import (
    DEFAULT_ARIMA_CONFIG,
    DEFAULT_LAG_REGRESSION_CONFIG,
    ArimaConfig,
    LagRegressionConfig,
    ModelId,
)
from backend.app.forecasting.real.domain import OhlcvRecord
from backend.app.forecasting.real.features.regression_features import build_regression_dataset
from backend.app.forecasting.real.history import load_company_ohlcv_history
from backend.app.forecasting.real.models.arima import ArimaSpecification
from backend.app.forecasting.real.training.refit_arima import refit_arima_for_production
from backend.app.forecasting.real.training.refit_lir import refit_lir_for_production
from backend.app.models.company import Company

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("pse_pulse_model_refit")

OFFICIAL_15_SYMBOLS = (
    "AC", "AEV", "ALI", "BDO", "BPI", "GLO", "ICT", "JFC",
    "MBCO", "MBT", "MER", "PGOLD", "SM", "SMPH", "TEL",
)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PSE Pulse Offline Model Refit and Artifact Bundle Builder"
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default="ALL",
        help="Comma-separated list of symbols (or 'ALL' for all tracked companies)",
    )
    parser.add_argument(
        "--models",
        type=str,
        default="LAG_REGRESSION,ARIMA",
        help="Comma-separated list of models to fit ('LAG_REGRESSION', 'ARIMA', or 'ALL')",
    )
    parser.add_argument(
        "--bundle-version",
        type=str,
        default="2026.03.01-v1",
        help="Version string for the artifact bundle (e.g. '2026.03.01-v1')",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("backend/artifacts/models"),
        help="Base directory where artifact bundle will be stored",
    )
    parser.add_argument(
        "--source-commit",
        type=str,
        default="b8bf39f8e94729687c2e877dc164ea8a4f69e2b1",
        help="Git commit of official source code / research baseline",
    )
    parser.add_argument(
        "--source-repo",
        type=str,
        default="AlvinTubtub/Capstone2-A4103-DigitalDelvers-SY26-27",
        help="Repository of official source code / research baseline",
    )
    parser.add_argument(
        "--historical-data-source-repo",
        type=str,
        default="AlvinTubtub/Capstone2-A4103-DigitalDelvers-SY26-27",
        help="Repository of historical OHLCV training data provenance",
    )
    parser.add_argument(
        "--historical-data-source-commit",
        type=str,
        default="b8bf39f8e94729687c2e877dc164ea8a4f69e2b1",
        help="Git commit of historical OHLCV training data provenance",
    )
    parser.add_argument(
        "--test-only-smoke",
        action="store_true",
        help="Enable bounded, fast refit parameters for testing/smoke validation",
    )
    parser.add_argument(
        "--lir-alpha",
        type=float,
        default=0.001,
        help="Selected LASSO L1 regularization strength for LIR refit",
    )
    parser.add_argument(
        "--arima-p",
        type=int,
        default=1,
        help="Selected AR order p for production ARIMA",
    )
    parser.add_argument(
        "--arima-d",
        type=int,
        default=1,
        help="Selected differencing order d for production ARIMA",
    )
    parser.add_argument(
        "--arima-q",
        type=int,
        default=0,
        help="Selected MA order q for production ARIMA",
    )
    parser.add_argument(
        "--arima-trend",
        type=str,
        default="n",
        help="Selected deterministic trend for production ARIMA ('n', 'c', 't', 'ct')",
    )
    return parser.parse_args(argv)


def run_refit(
    symbols: Sequence[str],
    model_types: Sequence[str],
    bundle_version: str,
    output_dir: Path,
    source_commit: str,
    source_repo: str,
    historical_data_source_repo: str = "AlvinTubtub/Capstone2-A4103-DigitalDelvers-SY26-27",
    historical_data_source_commit: str = "b8bf39f8e94729687c2e877dc164ea8a4f69e2b1",
    test_only_smoke: bool = False,
    lir_alpha: float = 0.001,
    arima_order: tuple[int, int, int] = (1, 1, 0),
    arima_trend: str = "n",
) -> int:
    """Execute offline refitting and persist versioned artifacts."""
    db = SessionLocal()
    bundle_root = output_dir.resolve() / bundle_version

    logger.info("Starting model refit into %s", bundle_root)
    logger.info("Target symbols: %s", symbols)
    logger.info("Target models: %s", model_types)
    logger.info("Bundle version: %s", bundle_version)

    total_trained = 0
    errors: List[str] = []

    try:
        # Resolve company records
        for symbol in symbols:
            company = db.query(Company).filter(Company.symbol == symbol).first()
            if not company:
                logger.warning("Company %s not found in database. Skipping.", symbol)
                continue

            records = load_company_ohlcv_history(db, company.id)
            if not records:
                logger.warning("No OHLCV history found for %s. Skipping.", symbol)
                continue

            symbol_dir = bundle_root / symbol
            symbol_dir.mkdir(parents=True, exist_ok=True)
            trained_through = records[-1].trading_date
            row_count = len(records)

            logger.info(
                "Refitting %s (%d records, trained_through=%s)",
                symbol,
                row_count,
                trained_through,
            )

            # 1. Refit LIR if requested
            if any(m.upper() in ("LAG_REGRESSION", "LAG_REG", "LIR") for m in model_types):
                try:
                    lir_config = DEFAULT_LAG_REGRESSION_CONFIG
                    if test_only_smoke:
                        # Fast smoke test settings
                        lir_config = LagRegressionConfig(
                            max_iterations=1000,
                            tolerance=1e-4,
                        )

                    dataset = build_regression_dataset(
                        records=records,
                        config=lir_config.features,
                    )

                    fitted_lir = refit_lir_for_production(
                        dataset=dataset,
                        chosen_alpha=lir_alpha,
                        config=lir_config,
                    )

                    hyperparameters = {
                        "alpha": lir_alpha,
                        "feature_names": list(fitted_lir.fit_metadata.feature_names),
                        "pacf_selected_lags": list(fitted_lir.pacf_selected_lags),
                        "hyperparameter_regime": "TEST_ONLY" if test_only_smoke else "NON_AUTHORITATIVE",
                        "test_only_smoke": test_only_smoke,
                    }

                    meta, m_path, meta_path = persist_model_artifact(
                        output_directory=symbol_dir,
                        symbol=symbol,
                        model_code="LAG_REGRESSION",
                        model_version=bundle_version,
                        fitted_model=fitted_lir,
                        hyperparameters=hyperparameters,
                        trained_through=trained_through,
                        data_row_count=row_count,
                        source_repository=source_repo,
                        source_commit=source_commit,
                        historical_data_source_repository=historical_data_source_repo,
                        historical_data_source_commit=historical_data_source_commit,
                    )
                    total_trained += 1
                    logger.info("Persisted LIR for %s: sha256=%s", symbol, meta.artifact_sha256)

                except Exception as exc:
                    err_msg = f"Failed to refit LIR for {symbol}: {exc}"
                    logger.error(err_msg, exc_info=True)
                    errors.append(err_msg)

            # 2. Refit ARIMA if requested
            if any(m.upper() in ("ARIMA",) for m in model_types):
                try:
                    arima_config = DEFAULT_ARIMA_CONFIG
                    if test_only_smoke:
                        arima_config = ArimaConfig(
                            retry_max_iterations=(50, 100),
                            require_confirmed_convergence=False,
                        )

                    spec = ArimaSpecification(
                        order=arima_order,
                        trend=arima_trend,
                    )

                    fitted_arima = refit_arima_for_production(
                        records=records,
                        selected_specification=spec,
                        config=arima_config,
                    )

                    hyperparameters = {
                        "order": list(arima_order),
                        "trend": arima_trend,
                        "hyperparameter_regime": "TEST_ONLY" if test_only_smoke else "NON_AUTHORITATIVE",
                        "test_only_smoke": test_only_smoke,
                    }

                    meta, m_path, meta_path = persist_model_artifact(
                        output_directory=symbol_dir,
                        symbol=symbol,
                        model_code="ARIMA",
                        model_version=bundle_version,
                        fitted_model=fitted_arima.model,
                        hyperparameters=hyperparameters,
                        trained_through=trained_through,
                        data_row_count=row_count,
                        source_repository=source_repo,
                        source_commit=source_commit,
                        historical_data_source_repository=historical_data_source_repo,
                        historical_data_source_commit=historical_data_source_commit,
                    )
                    total_trained += 1
                    logger.info("Persisted ARIMA for %s: sha256=%s", symbol, meta.artifact_sha256)

                except Exception as exc:
                    err_msg = f"Failed to refit ARIMA for {symbol}: {exc}"
                    logger.error(err_msg, exc_info=True)
                    errors.append(err_msg)

        logger.info(
            "Refit complete. Successfully trained & persisted %d artifacts. Errors: %d",
            total_trained,
            len(errors),
        )
        return 0 if not errors else 1

    finally:
        db.close()


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)

    symbols = (
        OFFICIAL_15_SYMBOLS
        if args.symbols.strip().upper() == "ALL"
        else [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    )

    model_types = (
        ["LAG_REGRESSION", "ARIMA"]
        if args.models.strip().upper() == "ALL"
        else [m.strip().upper() for m in args.models.split(",") if m.strip()]
    )

    exit_code = run_refit(
        symbols=symbols,
        model_types=model_types,
        bundle_version=args.bundle_version,
        output_dir=args.output_dir,
        source_commit=args.source_commit,
        source_repo=args.source_repo,
        historical_data_source_repo=args.historical_data_source_repo,
        historical_data_source_commit=args.historical_data_source_commit,
        test_only_smoke=args.test_only_smoke,
        lir_alpha=args.lir_alpha,
        arima_order=(args.arima_p, args.arima_d, args.arima_q),
        arima_trend=args.arima_trend,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
