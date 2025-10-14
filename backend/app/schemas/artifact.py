from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import Field

from app.schemas.base import CamelInBaseModel, CamelOutBaseModel


class Kind(str, Enum):
    """Enumeration of possible artifact types."""

    OUTPUT = "output"
    ARCHIVE = "archive"
    RUN_SCRIPT = "run_script"
    POSTPROCESS_SCRIPT = "postprocessing_script"


class ArtifactCreate(CamelInBaseModel):
    kind: Kind = Field(..., description="The type of the artifact.")
    uri: str = Field(..., description="The URI where the artifact is located.")
    label: str | None = Field(None, description="An optional label for the artifact.")


class ArtifactOut(CamelOutBaseModel):
    id: UUID = Field(..., description="The unique identifier of the artifact.")

    kind: Kind = Field(..., description="The type of the artifact.")
    uri: str = Field(..., description="The URI where the artifact is located.")
    label: str | None = Field(None, description="An optional label for the artifact.")

    created_at: datetime = Field(
        ..., description="The timestamp when the artifact was created."
    )
    updated_at: datetime = Field(
        ..., description="The timestamp when the artifact was last updated."
    )
