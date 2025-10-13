from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.artifact import ArtifactIn, ArtifactOut
from app.schemas.base import CamelInModel, CamelOutModel
from app.schemas.link import ExternalLinkIn, ExternalLinkOut


class SimulationCreate(CamelInModel):
    # Configuration
    # ~~~~~~~~~~~~~~
    name: str = Field(..., description="Name of the simulation")
    case_name: str = Field(..., description="Case name associated with the simulation")
    description: str | None = Field(
        None, description="Optional description of the simulation"
    )
    version_tag: str | None = Field(
        None, description="Optional version tag for the simulation"
    )
    git_hash: str | None = Field(
        None, description="Git hash associated with the simulation"
    )
    compset: str = Field(..., description="Component set used in the simulation")
    compset_alias: str = Field(..., description="Alias for the component set")
    grid_name: str = Field(..., description="Grid name used in the simulation")
    grid_resolution: str = Field(
        ..., description="Grid resolution used in the simulation"
    )
    parent_simulation_id: UUID | None = Field(
        None, description="ID of the parent simulation, if any"
    )

    # Model setup/context
    # ~~~~~~~~~~~~~~~~~~~
    # TODO: Make simulation_type an Enum once we have a fixed set of types.
    simulation_type: str = Field(..., description="Type of the simulation")
    status: str = Field(..., description="Current status of the simulation")
    campaign_id: str | None = Field(
        None, description="ID of the associated campaign, if any"
    )
    experiment_type_id: str | None = Field(
        None, description="ID of the experiment type, if any"
    )
    initialization_type: str = Field(
        ..., description="Initialization type for the simulation"
    )
    group_name: str | None = Field(
        None, description="Group name associated with the simulation, if any"
    )

    # Model timeline
    # ~~~~~~~~~~~~~~
    machine_id: UUID = Field(
        ..., description="ID of the machine used for the simulation"
    )
    simulation_start_date: datetime = Field(
        ..., description="Start date of the simulation"
    )
    simulation_end_date: datetime | None = Field(
        None, description="End date of the simulation, if any"
    )
    run_start_date: datetime | None = Field(
        None, description="Start date of the simulation run, if any"
    )
    run_end_date: datetime | None = Field(
        None, description="End date of the simulation run, if any"
    )
    compiler: str | None = Field(
        None, description="Compiler used for the simulation, if any"
    )

    # Metadata & audit
    # ~~~~~~~~~~~~~~~~~
    key_features: str | None = Field(
        None, description="Key features of the simulation, if any"
    )
    known_issues: str | None = Field(
        None, description="Known issues with the simulation, if any"
    )
    notes_markdown: str | None = Field(
        None, description="Additional notes in markdown format, if any"
    )

    # Version control
    # ~~~~~~~~~~~~~~~
    branch: str | None = Field(
        None, description="Branch name associated with the simulation, if any"
    )
    external_repo_url: str | None = Field(
        None, description="URL of the external repository, if any"
    )

    # Provenance & submission
    # ~~~~~~~~~~~~~~~~~~~~~~~
    created_by: str | None = Field(
        None, description="User who created the simulation, if any"
    )
    last_updated_by: str | None = Field(
        None, description="User who last updated the simulation, if any"
    )

    # Miscellaneous
    # ~~~~~~~~~~~~~~~~~
    extra: dict = Field(
        default_factory=dict,
        description="Extra metadata in flexible dictionary/JSON format",
    )

    # Relationships
    # ~~~~~~~~~~~~~~
    artifacts: list[ArtifactIn] = Field(
        default_factory=list,
        description="List of artifacts associated with the simulation",
    )
    links: list[ExternalLinkIn] = Field(
        default_factory=list,
        description="List of external links associated with the simulation",
    )


class SimulationOut(CamelOutModel):
    # Configuration
    # ~~~~~~~~~~~~~~
    id: UUID = Field(..., description="Unique identifier for the simulation")
    name: str = Field(..., description="Name of the simulation")
    case_name: str = Field(..., description="Case name associated with the simulation")
    description: str | None = Field(
        None, description="Optional description of the simulation"
    )
    version_tag: str | None = Field(
        None, description="Optional version tag for the simulation"
    )
    git_hash: str | None = Field(
        None, description="Git hash associated with the simulation"
    )
    compset: str = Field(..., description="Component set used in the simulation")
    compset_alias: str = Field(..., description="Alias for the component set")
    grid_name: str = Field(..., description="Grid name used in the simulation")
    grid_resolution: str = Field(
        ..., description="Grid resolution used in the simulation"
    )
    parent_simulation_id: UUID | None = Field(
        None, description="ID of the parent simulation, if any"
    )

    # Model setup/context
    # ~~~~~~~~~~~~~~~~~~~
    # TODO: Make simulation_type an Enum once we have a fixed set of types.
    simulation_type: str = Field(..., description="Type of the simulation")
    status: str = Field(..., description="Current status of the simulation")
    campaign_id: str | None = Field(
        None, description="ID of the associated campaign, if any"
    )
    experiment_type_id: str | None = Field(
        None, description="ID of the experiment type, if any"
    )
    initialization_type: str = Field(
        ..., description="Initialization type for the simulation"
    )
    group_name: str | None = Field(
        None, description="Group name associated with the simulation, if any"
    )

    # Model timeline
    # ~~~~~~~~~~~~~~
    machine_id: UUID = Field(
        ..., description="ID of the machine used for the simulation"
    )
    simulation_start_date: datetime = Field(
        ..., description="Start date of the simulation"
    )
    simulation_end_date: datetime | None = Field(
        None, description="End date of the simulation, if any"
    )
    total_years: float | None = Field(None, description="Total years simulated, if any")
    run_start_date: datetime | None = Field(
        None, description="Start date of the simulation run, if any"
    )
    run_end_date: datetime | None = Field(
        None, description="End date of the simulation run, if any"
    )
    compiler: str | None = Field(
        None, description="Compiler used for the simulation, if any"
    )

    # Metadata & audit
    # ~~~~~~~~~~~~~~~~~
    key_features: str | None = Field(
        None, description="Key features of the simulation, if any"
    )
    known_issues: str | None = Field(
        None, description="Known issues with the simulation, if any"
    )
    notes_markdown: str | None = Field(
        None, description="Additional notes in markdown format, if any"
    )

    # Version control
    # ~~~~~~~~~~~~~~~
    branch: str | None = Field(
        None, description="Branch name associated with the simulation, if any"
    )
    external_repo_url: str | None = Field(
        None, description="URL of the external repository, if any"
    )

    # Provenance & submission
    # ~~~~~~~~~~~~~~~~~~~~~~~
    created_at: datetime = Field(
        ..., description="Timestamp when the simulation was created"
    )
    created_by: str | None = Field(
        None, description="User who created the simulation, if any"
    )
    updated_at: datetime = Field(
        ..., description="Timestamp when the simulation was last updated"
    )
    last_updated_by: str | None = Field(
        None, description="User who last updated the simulation, if any"
    )

    # Miscellaneous
    # ~~~~~~~~~~~~~~~~~
    extra: dict = Field(
        default_factory=dict,
        description="Extra metadata in flexible dictionary/JSON format",
    )

    # Relationships
    # ~~~~~~~~~~~~~~
    artifacts: list[ArtifactOut] = Field(
        default_factory=list,
        description="List of artifacts associated with the simulation",
    )
    links: list[ExternalLinkOut] = Field(
        default_factory=list,
        description="List of external links associated with the simulation",
    )
