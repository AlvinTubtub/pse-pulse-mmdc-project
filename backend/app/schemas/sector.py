"""Sector Pydantic schemas."""

from typing import Optional
from backend.app.schemas.common import BaseSchema


class SectorBase(BaseSchema):
    name: str
    code: str
    description: Optional[str] = None


class SectorRead(SectorBase):
    id: int
