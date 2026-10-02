"""ModelArtifact SQLAlchemy model for versioned model-binary lineage."""

from datetime import datetime, timezone
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from backend.app.database import Base


class ModelArtifact(Base):
    __tablename__ = "model_artifacts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    model_metadata_id = Column(Integer, ForeignKey("model_metadata.id"), nullable=False, index=True)

    bundle_version = Column(String(50), nullable=False, index=True)
    artifact_format = Column(String(30), nullable=False, default="joblib")
    artifact_path = Column(String(500), nullable=False)
    artifact_sha256 = Column(String(64), nullable=False, index=True)

    trained_through = Column(Date, nullable=False)
    data_row_count = Column(Integer, nullable=False)

    hyperparameters_json = Column(Text, nullable=False)

    source_repository = Column(String(500), nullable=False)
    source_commit = Column(String(40), nullable=False)
    historical_data_source_repository = Column(String(500), nullable=False)
    historical_data_source_commit = Column(String(40), nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    is_active = Column(Boolean, default=True, nullable=False)

    company = relationship("Company", backref="model_artifacts")
    model_metadata = relationship("ModelMetadata", backref="model_artifacts")
    forecasts = relationship("Forecast", back_populates="model_artifact")

    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "model_metadata_id",
            "bundle_version",
            name="uq_model_artifact_company_model_bundle",
        ),
        Index("ix_model_artifacts_company_model", "company_id", "model_metadata_id"),
    )
