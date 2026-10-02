"""Models metadata endpoints."""

from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models.model_metadata import ModelMetadata
from backend.app.schemas.forecast import ModelMetadataRead

router = APIRouter()


@router.get("", response_model=List[ModelMetadataRead])
def list_models(db: Session = Depends(get_db)):
    """Retrieve metadata on available forecasting models and stubs."""
    models = db.query(ModelMetadata).filter(ModelMetadata.is_active == True).all()
    return [
        ModelMetadataRead(
            id=m.id,
            name=m.name,
            code=m.code,
            version=m.version,
            description=m.description,
            is_active=m.is_active,
        )
        for m in models
    ]
