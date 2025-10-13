from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import Field, HttpUrl

from app.schemas.base import CamelInModel, CamelOutModel


class Kind(str, Enum):
    DIAGNOSTIC = "diagnostic"
    PERFORMANCE = "performance"
    DOCS = "docs"
    OTHER = "other"


class ExternalLinkIn(CamelInModel):
    kind: Kind = Field(..., description="The type of the external link.")
    url: HttpUrl = Field(..., description="The URL of the external link.")
    label: str | None = Field(
        None, description="An optional label for the external link."
    )


class ExternalLinkOut(CamelOutModel):
    id: UUID = Field(..., description="The unique identifier of the external link.")

    kind: Kind = Field(..., description="The type of the external link.")
    url: HttpUrl = Field(..., description="The URL of the external link.")
    label: str | None = Field(
        None, description="An optional label for the external link."
    )

    created_at: datetime = Field(
        ..., description="The timestamp when the external link was created."
    )
    updated_at: datetime = Field(
        ..., description="The timestamp when the external link was last updated."
    )
