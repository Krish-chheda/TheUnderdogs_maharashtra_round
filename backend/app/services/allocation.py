import hashlib
import hmac
import json
import logging
import secrets
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from math import floor

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import redis_client
from app.models.base import Allocation, AllocationRun, Entry, Event

logger = logging.getLogger("allocation")

DEFAULT_BATCH_DURATION_SECONDS = 120
DEFAULT_BATCH_WEIGHTS = (0.30, 0.25, 0.20, 0.15, 0.10)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def effective_weights(batch_count: int, configured: list[float] | None) -> list[float]:
    source = [float(value) for value in (configured or DEFAULT_BATCH_WEIGHTS) if float(value) > 0]
    if not source:
        raise ValueError("Allocation policy must contain a positive batch weight")
    if len(source) < batch_count:
        source.extend([source[-1]] * (batch_count - len(source)))
    weights = source[:batch_count]
    total = sum(weights)
    return [weight / total for weight in weights]


def calculate_quotas(counts: dict[int, int], capacity: int, configured: list[float] | None) -> dict[int, int]:
    batch_count = max(counts, default=-1) + 1
    if batch_count <= 0 or capacity <= 0:
        return {}
    target = min(capacity, sum(counts.values()))
    weights = effective_weights(batch_count, configured)
    raw = [target * weight for weight in weights]
    quotas = [floor(value) for value in raw]
    for index in sorted(range(batch_count), key=lambda item: (-(raw[item] - quotas[item]), item))[: target - sum(quotas)]:
        quotas[index] += 1

    selected = [min(quotas[index], counts.get(index, 0)) for index in range(batch_count)]
    remaining = target - sum(selected)
    while remaining:
        candidates = [index for index in range(batch_count) if selected[index] < counts.get(index, 0)]
        if not candidates:
            break
        candidates.sort(key=lambda index: (-weights[index], index))
        for index in candidates:
            if not remaining:
                break
            selected[index] += 1
            remaining -= 1
    return {index: selected[index] for index in range(batch_count)}


def randomized_order(entries: list[Entry], seed: bytes) -> list[Entry]:
    return sorted(
        entries,
        key=lambda entry: hmac.new(seed, str(entry.id).encode("utf-8"), hashlib.sha256).hexdigest(),
    )


def batch_entries(entries: list[Entry], event: Event) -> dict[int, list[Entry]]:
    start = as_utc(event.registration_start or event.created_at)
    duration = event.batch_duration_seconds or DEFAULT_BATCH_DURATION_SECONDS
    grouped: dict[int, list[Entry]] = defaultdict(list)
    for entry in entries:
        elapsed = max(0, (as_utc(entry.joined_at) - start).total_seconds())
        grouped[int(elapsed // duration)].append(entry)
    return grouped


async def commit_allocation(db: AsyncSession, event_id: uuid.UUID) -> dict:
    """
    Phase 11: True Pre-Draw Commitment.
    Generates cryptographically secure seed and its immutable commitment BEFORE draw.
    Saves immutable record in PostgreSQL.
    """
    event = await db.scalar(select(Event).where(Event.id == event_id).with_for_update())
    if not event:
        raise ValueError("Event not found")

    existing_run = await db.scalar(select(AllocationRun).where(AllocationRun.event_id == event_id))
    if existing_run:
        return {
            "status": existing_run.status,
            "allocation_run_id": str(existing_run.id),
            "seed_commitment": existing_run.seed_commitment,
            "entry_list_hash": existing_run.entry_list_hash,
            "commitment_created_at": existing_run.commitment_created_at.isoformat() if existing_run.commitment_created_at else None,
            "eligible_entry_count": existing_run.eligible_entry_count,
            "batch_definitions": existing_run.batch_definitions,
        }

    now = datetime.now(timezone.utc)
    # Registration must be closed to commit
    event.is_open = False

    entries = list((await db.scalars(
        select(Entry).where(Entry.event_id == event_id, Entry.status == "ELIGIBLE").order_by(Entry.joined_at, Entry.id)
    )).all())

    seed = secrets.token_bytes(32)
    seed_hex = seed.hex()
    seed_commitment = hashlib.sha256(seed).hexdigest()

    entry_ids = "".join(str(entry.id) for entry in entries)
    entry_list_hash = hashlib.sha256(entry_ids.encode("utf-8")).hexdigest()

    groups = batch_entries(entries, event)
    counts = {index: len(items) for index, items in groups.items()}
    configured_weights = event.batch_weights or list(DEFAULT_BATCH_WEIGHTS)
    quotas = calculate_quotas(counts, event.capacity, configured_weights)
    batch_count = max(counts, default=-1) + 1
    weights = effective_weights(batch_count, configured_weights) if batch_count else []
    batch_definitions = [
        {"batch_id": f"batch-{i + 1}", "entry_count": counts.get(i, 0), "quota": quotas.get(i, 0), "weight": weights[i]}
        for i in range(batch_count)
    ]

    allocation_run = AllocationRun(
        event_id=event.id,
        allocation_seed=seed_hex,
        seed_commitment=seed_commitment,
        revealed_seed=None,
        commitment_created_at=now,
        batch_duration_seconds=event.batch_duration_seconds or DEFAULT_BATCH_DURATION_SECONDS,
        allocation_policy={"weights": weights, "redistribution": "deterministic_weight_order"},
        batch_definitions=batch_definitions,
        entry_list_hash=entry_list_hash,
        eligible_entry_count=len(entries),
        winner_count=0,
        waitlist_count=0,
        status="COMMITTED",
        result_json="{}",
    )
    db.add(allocation_run)
    await db.commit()
    await db.refresh(allocation_run)

    return {
        "status": "COMMITTED",
        "allocation_run_id": str(allocation_run.id),
        "seed_commitment": seed_commitment,
        "entry_list_hash": entry_list_hash,
        "commitment_created_at": now.isoformat(),
        "eligible_entry_count": len(entries),
        "batch_definitions": batch_definitions,
    }


async def allocate_event(db: AsyncSession, event_id: uuid.UUID) -> dict:
    """
    Executes the allocation draw using the pre-committed seed.
    Reveals the seed, assigns winners/waitlist, generates canonical audit hash,
    and permanently stores in PostgreSQL.
    """
    event = await db.scalar(select(Event).where(Event.id == event_id).with_for_update())
    if not event:
        raise ValueError("Event not found")

    existing_run = await db.scalar(select(AllocationRun).where(AllocationRun.event_id == event_id).with_for_update())
    if existing_run and existing_run.status == "COMPLETED":
        return json.loads(existing_run.result_json)

    now = datetime.now(timezone.utc)
    if event.is_open and (not event.registration_deadline or as_utc(event.registration_deadline) > now):
        raise ValueError("Registration must be closed before allocation")
    event.is_open = False

    # If no pre-commitment existed, create it now to ensure two-phase invariant
    if not existing_run:
        commit_res = await commit_allocation(db, event_id)
        existing_run = await db.scalar(select(AllocationRun).where(AllocationRun.event_id == event_id).with_for_update())

    seed = bytes.fromhex(existing_run.allocation_seed)
    seed_hex = seed.hex()
    
    # Cryptographic integrity check: Seed must match commitment
    assert hashlib.sha256(seed).hexdigest() == existing_run.seed_commitment, "Seed does not match pre-commitment!"

    entries = list((await db.scalars(
        select(Entry).where(Entry.event_id == event_id, Entry.status == "ELIGIBLE").order_by(Entry.joined_at, Entry.id)
    )).all())

    groups = batch_entries(entries, event)
    counts = {index: len(items) for index, items in groups.items()}
    configured_weights = event.batch_weights or list(DEFAULT_BATCH_WEIGHTS)
    quotas = calculate_quotas(counts, event.capacity, configured_weights)
    batch_count = max(counts, default=-1) + 1
    weights = effective_weights(batch_count, configured_weights) if batch_count else []

    winners: list[Entry] = []
    waitlisted: list[Entry] = []
    batch_definitions = []
    for index in range(batch_count):
        ordered = randomized_order(groups.get(index, []), seed)
        for position, entry in enumerate(ordered, start=1):
            entry.batch_id = f"batch-{index + 1}"
            entry.randomized_position = position
        selected = ordered[: quotas.get(index, 0)]
        winners.extend(selected)
        waitlisted.extend(ordered[quotas.get(index, 0):])
        batch_definitions.append({
            "batch_id": f"batch-{index + 1}",
            "entry_count": len(ordered),
            "quota": quotas.get(index, 0),
            "weight": weights[index]
        })

    # Reveal seed and update allocation run
    existing_run.revealed_seed = seed_hex
    existing_run.winner_count = len(winners)
    existing_run.waitlist_count = len(waitlisted)
    existing_run.allocated_at = now
    existing_run.allocation_executed_at = now
    existing_run.batch_definitions = batch_definitions
    existing_run.status = "COMPLETED"

    # Insert allocations
    allocations = []
    for rank, entry in enumerate(winners + waitlisted, start=1):
        allocation_status = "WINNER" if entry in winners else "WAITLISTED"
        entry.allocation_status = allocation_status
        entry.allocated_at = now
        allocations.append({
            "event_id": event.id,
            "user_id": entry.user_id,
            "rank": rank,
            "status": allocation_status,
            "claim_expires_at": now + timedelta(hours=24) if allocation_status == "WINNER" else None,
            "allocation_run_id": existing_run.id
        })
    if allocations:
        await db.execute(Allocation.__table__.insert(), allocations)

    # Deterministic Canonical JSON serialization for hashing
    canonical_payload = {
        "allocation_run_id": str(existing_run.id),
        "capacity": event.capacity,
        "commitment_created_at": existing_run.commitment_created_at.isoformat() if existing_run.commitment_created_at else now.isoformat(),
        "eligible_entry_count": len(entries),
        "entry_list_hash": existing_run.entry_list_hash,
        "event_id": str(event.id),
        "revealed_seed": seed_hex,
        "seed_commitment": existing_run.seed_commitment,
        "seed_verified": True,
        "status": "ALLOCATION_COMPLETE",
        "waitlist_count": len(waitlisted),
        "winner_count": len(winners),
        "winners_by_batch": {f"batch-{index + 1}": quotas.get(index, 0) for index in range(batch_count)},
    }
    canonical_json_bytes = json.dumps(canonical_payload, sort_keys=True, separators=(',', ':')).encode("utf-8")
    result_hash = hashlib.sha256(canonical_json_bytes).hexdigest()

    existing_run.allocation_result_hash = result_hash
    
    # Store complete audit record with result hash
    full_result = {
        **canonical_payload,
        "allocation_result_hash": result_hash,
        "allocation_executed_at": now.isoformat(),
        "batch_definitions": batch_definitions,
        "winners": len(winners),
        "waitlisted": len(waitlisted),
    }
    existing_run.result_json = json.dumps(full_result)
    
    # Commit permanently to PostgreSQL
    await db.commit()

    # Cache in Redis for quick lookup
    try:
        await redis_client.set(f"audit:{event_id}", json.dumps(full_result))
    except Exception as e:
        logger.warning(f"Could not cache audit proof in Redis: {e}")

    return full_result
