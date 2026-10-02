"""Database persistence and storage snapshot scaffold for pipeline runs."""

from datetime import datetime, timezone
from typing import List, Dict, Any
from sqlalchemy.orm import Session
import logging

from backend.app.models.pipeline_run import PipelineRun
from backend.app.models.forecast import Forecast
from backend.app.models.model_metadata import ModelMetadata
from backend.app.forecasting.base import InferencePoint

logger = logging.getLogger(__name__)


class DatabaseSaver:
    """Handles persisting pipeline execution outputs to PostgreSQL / SQLite."""

    def __init__(self, db: Session):
        self.db = db

    def create_run_record(self, is_demo: bool = True) -> PipelineRun:
        """Initialize a new PipelineRun record."""
        run = PipelineRun(
            status="RUNNING",
            started_at=datetime.now(timezone.utc),
            is_demo_run=is_demo,
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def finish_run_record(
        self,
        run_id: str,
        status: str,
        records_ingested: int = 0,
        forecasts_generated: int = 0,
        error_message: str | None = None,
    ) -> PipelineRun | None:
        """Mark a pipeline run as completed or failed."""
        run = self.db.query(PipelineRun).filter(PipelineRun.run_id == run_id).first()
        if not run:
            return None

        run.status = status
        run.completed_at = datetime.now(timezone.utc)
        run.records_ingested = records_ingested
        run.forecasts_generated = forecasts_generated
        run.error_message = error_message

        self.db.commit()
        self.db.refresh(run)
        return run

    def persist_forecasts(
        self,
        company_id: int,
        model_forecasts: Dict[str, List[InferencePoint]],
        pipeline_run_id: int | None = None,
    ) -> int:
        """Persist generated forecasts into database."""
        count = 0
        for code, points in model_forecasts.items():
            model_meta = self.db.query(ModelMetadata).filter(ModelMetadata.code == code).first()
            if not model_meta:
                continue

            for pt in points:
                # Check for existing record on company_id, model_id, target_date, pipeline_run_id
                existing = (
                    self.db.query(Forecast)
                    .filter(
                        Forecast.company_id == company_id,
                        Forecast.model_id == model_meta.id,
                        Forecast.target_date == pt.target_date,
                        Forecast.pipeline_run_id == pipeline_run_id,
                    )
                    .first()
                )

                if existing:
                    existing.predicted_price = pt.predicted_price
                    existing.lower_bound = pt.lower_bound
                    existing.upper_bound = pt.upper_bound
                    existing.confidence_level = pt.confidence_level
                    existing.is_demo = pt.is_demo
                else:
                    new_fc = Forecast(
                        company_id=company_id,
                        model_id=model_meta.id,
                        pipeline_run_id=pipeline_run_id,
                        target_date=pt.target_date,
                        predicted_price=pt.predicted_price,
                        lower_bound=pt.lower_bound,
                        upper_bound=pt.upper_bound,
                        confidence_level=pt.confidence_level,
                        is_demo=pt.is_demo,
                    )
                    self.db.add(new_fc)
                count += 1

        self.db.commit()
        return count
