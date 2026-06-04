from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.features.simulation.models import Simulation

SubgroupKey = tuple[UUID, str]


@dataclass(frozen=True)
class AnchorRunState:
    is_anchor_run: bool
    anchor_simulation_id: UUID | None


def resolve_anchor_run_state(
    db: Session,
    simulation: Simulation,
) -> AnchorRunState:
    states = resolve_anchor_run_states(db, [simulation])
    if simulation.id is None:
        return AnchorRunState(is_anchor_run=False, anchor_simulation_id=None)

    return states.get(
        simulation.id,
        AnchorRunState(is_anchor_run=False, anchor_simulation_id=None),
    )


async def resolve_anchor_run_state_async(
    db: AsyncSession,
    simulation: Simulation,
) -> AnchorRunState:
    states = await resolve_anchor_run_states_async(db, [simulation])
    if simulation.id is None:
        return AnchorRunState(is_anchor_run=False, anchor_simulation_id=None)

    return states.get(
        simulation.id,
        AnchorRunState(is_anchor_run=False, anchor_simulation_id=None),
    )


def resolve_anchor_run_states(
    db: Session,
    simulations: Sequence[Simulation],
) -> dict[UUID, AnchorRunState]:
    subgroup_keys = {
        (simulation.case_id, simulation.case_hash)
        for simulation in simulations
        if simulation.id is not None and simulation.case_hash is not None
    }
    anchor_ids = _load_subgroup_anchor_ids(db, subgroup_keys)
    states: dict[UUID, AnchorRunState] = {}

    for simulation in simulations:
        if simulation.id is None:
            continue

        if simulation.case_hash is None:
            states[simulation.id] = AnchorRunState(
                is_anchor_run=False,
                anchor_simulation_id=None,
            )
            continue

        anchor_simulation_id = anchor_ids.get(
            (simulation.case_id, simulation.case_hash)
        )
        states[simulation.id] = AnchorRunState(
            is_anchor_run=anchor_simulation_id == simulation.id,
            anchor_simulation_id=anchor_simulation_id,
        )

    return states


async def resolve_anchor_run_states_async(
    db: AsyncSession,
    simulations: Sequence[Simulation],
) -> dict[UUID, AnchorRunState]:
    subgroup_keys = {
        (simulation.case_id, simulation.case_hash)
        for simulation in simulations
        if simulation.id is not None and simulation.case_hash is not None
    }
    anchor_ids = await _load_subgroup_anchor_ids_async(db, subgroup_keys)
    states: dict[UUID, AnchorRunState] = {}

    for simulation in simulations:
        if simulation.id is None:
            continue

        if simulation.case_hash is None:
            states[simulation.id] = AnchorRunState(
                is_anchor_run=False,
                anchor_simulation_id=None,
            )
            continue

        anchor_simulation_id = anchor_ids.get(
            (simulation.case_id, simulation.case_hash)
        )
        states[simulation.id] = AnchorRunState(
            is_anchor_run=anchor_simulation_id == simulation.id,
            anchor_simulation_id=anchor_simulation_id,
        )

    return states


def _load_subgroup_anchor_ids(
    db: Session,
    subgroup_keys: set[SubgroupKey],
) -> dict[SubgroupKey, UUID]:
    if not subgroup_keys:
        return {}

    rows = db.execute(_build_anchor_ids_query(subgroup_keys)).all()

    return _map_anchor_rows(rows)


async def _load_subgroup_anchor_ids_async(
    db: AsyncSession,
    subgroup_keys: set[SubgroupKey],
) -> dict[SubgroupKey, UUID]:
    if not subgroup_keys:
        return {}

    rows = (await db.execute(_build_anchor_ids_query(subgroup_keys))).all()

    return _map_anchor_rows(rows)


def _build_anchor_ids_query(subgroup_keys: set[SubgroupKey]):
    ranked_subquery = (
        select(
            Simulation.case_id.label("case_id"),
            Simulation.case_hash.label("case_hash"),
            Simulation.id.label("simulation_id"),
            func.row_number()
            .over(
                partition_by=(Simulation.case_id, Simulation.case_hash),
                order_by=(Simulation.created_at.asc(), Simulation.id.asc()),
            )
            .label("row_number"),
        )
        .where(tuple_(Simulation.case_id, Simulation.case_hash).in_(subgroup_keys))
        .subquery()
    )

    return select(
        ranked_subquery.c.case_id,
        ranked_subquery.c.case_hash,
        ranked_subquery.c.simulation_id,
    ).where(ranked_subquery.c.row_number == 1)


def _map_anchor_rows(
    rows: Sequence[tuple[UUID, str | None, UUID]],
) -> dict[SubgroupKey, UUID]:
    return {
        (case_id, case_hash): simulation_id
        for case_id, case_hash, simulation_id in rows
        if case_hash is not None
    }
