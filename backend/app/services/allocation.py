import hashlib
import hmac
import json
import secrets
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from math import floor

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import redis_client
from app.models.base import Allocation, AllocationRun, Entry, Event

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


async def allocate_event(db: AsyncSession, event_id: uuid.UUID) -> dict:
    event = await db.scalar(select(Event).where(Event.id == event_id).with_for_update())
    if not event:
        raise ValueError("Event not found")

    existing_run = await db.scalar(select(AllocationRun).where(AllocationRun.event_id == event_id))
    if existing_run:
        return json.loads(existing_run.result_json)

    now = datetime.now(timezone.utc)
    if event.is_open and (not event.registration_deadline or as_utc(event.registration_deadline) > now):
        raise ValueError("Registration must be closed before allocation")
    event.is_open = False

    entries = list((await db.scalars(select(Entry).where(Entry.event_id == event_id, Entry.status == "ELIGIBLE").order_by(Entry.joined_at, Entry.id))).all())
    seed = secrets.token_bytes(32)
    seed_hex = seed.hex()
    groups = batch_entries(entries, event)
    counts = {index: len(items) for index, items in groups.items()}
    configured_weights = event.batch_weights or list(DEFAULT_BATCH_WEIGHTS)
    quotas = calculate_quotas(counts, event.capacity, configured_weights)
    batch_count = max(counts, default=-1) + 1
    weights = effective_weights(batch_count, configured_weights) if batch_count else []

    entry_ids = "".join(str(entry.id) for entry in entries)
    entry_list_hash = hashlib.sha256(entry_ids.encode("utf-8")).hexdigest()
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
        batch_definitions.append({"batch_id": f"batch-{index + 1}", "entry_count": len(ordered), "quota": quotas.get(index, 0), "weight": weights[index]})

    allocation_run = AllocationRun(
        event_id=event.id,
        allocation_seed=seed_hex,
        seed_commitment=hashlib.sha256(seed).hexdigest(),
        batch_duration_seconds=event.batch_duration_seconds or DEFAULT_BATCH_DURATION_SECONDS,
        allocation_policy={"weights": weights, "redistribution": "deterministic_weight_order"},
        batch_definitions=batch_definitions,
        entry_list_hash=entry_list_hash,
        eligible_entry_count=len(entries),
        winner_count=len(winners),
        waitlist_count=len(waitlisted),
        allocated_at=now,
        status="COMPLETED",
    )
    db.add(allocation_run)
    await db.flush()

    allocations = []
    for rank, entry in enumerate(winners + waitlisted, start=1):
        allocation_status = "WINNER" if entry in winners else "WAITLISTED"
        entry.allocation_status = allocation_status
        entry.allocated_at = now
        allocations.append({"event_id": event.id, "user_id": entry.user_id, "rank": rank, "status": allocation_status, "claim_expires_at": now + timedelta(hours=24) if allocation_status == "WINNER" else None, "allocation_run_id": allocation_run.id})
    if allocations:
        await db.execute(Allocation.__table__.insert(), allocations)

    result = {"status": "ALLOCATION_COMPLETE", "allocation_run_id": str(allocation_run.id), "winners": len(winners), "waitlisted": len(waitlisted), "winners_by_batch": {f"batch-{index + 1}": quotas.get(index, 0) for index in range(batch_count)}}
    allocation_run.result_json = json.dumps(result)
    await db.commit()
    await redis_client.set(f"audit:{event_id}", json.dumps({"allocation_run_id": str(allocation_run.id), "seed_commitment": allocation_run.seed_commitment, "entry_list_hash": entry_list_hash, "batch_definitions": batch_definitions, "winner_count": len(winners), "waitlist_count": len(waitlisted)}))
    return result
