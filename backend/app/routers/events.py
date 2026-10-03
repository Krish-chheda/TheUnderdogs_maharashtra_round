import uuid
from datetime import datetime, timezone
import json

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import func, select

from app.models.base import Event, Entry, Allocation, User, Reservation, AllocationRun
from app.core.database import get_db
from app.core.redis import redis_client
from app.core.config import settings

from app.dependencies.auth import get_current_user
from app.dependencies.fraud import anti_bot_farm, RiskLevel
from app.dependencies.rate_limit import check_multi_dim_rate_limits, check_token_bucket, get_client_ip

router = APIRouter(prefix="/events", tags=["events"])

def utc_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

def event_status(event: Event) -> str:
    now = datetime.now(timezone.utc)
    if event.event_date and event.registration_deadline and utc_time(event.registration_deadline) >= utc_time(event.event_date):
        return "Invalid schedule"
    if event.event_date and utc_time(event.event_date) <= now:
        return "Completed"
    if event.registration_deadline and utc_time(event.registration_deadline) < now:
        return "Closed"
    return "Open" if event.is_open else "Closed"

def serialize_event(event: Event, entry_count: int):
    schedule_valid = not event.event_date or not event.registration_deadline or utc_time(event.registration_deadline) < utc_time(event.event_date)
    return {
        "id": str(event.id),
        "name": event.name,
        "description": "Fair Drop allocation event.",
        "date": event.event_date.isoformat() if event.event_date else None,
        "timezone": "UTC",
        "registrationDeadline": event.registration_deadline.isoformat() if event.registration_deadline else None,
        "capacity": event.capacity,
        "entryCount": entry_count,
        "status": event_status(event),
        "venue": event.venue or "Fair Drop allocation system",
        "isOpen": event.is_open,
        "scheduleValid": schedule_valid,
        "scheduleError": None if schedule_valid else "Registration deadline must be before the event date.",
        "requiresPhoneVerification": getattr(event, "requires_phone_verification", False),
    }

@router.get("")
async def list_events(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Event, func.count(Entry.id))
        .outerjoin(Entry, Entry.event_id == Event.id)
        .group_by(Event.id)
        .order_by(Event.created_at.desc())
    )
    return [serialize_event(event, entry_count) for event, entry_count in result.all()]

@router.get("/{event_id}")
async def get_event(event_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Event, func.count(Entry.id))
        .outerjoin(Entry, Entry.event_id == Event.id)
        .where(Event.id == event_id)
        .group_by(Event.id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Event not found")
    event, entry_count = row
    return serialize_event(event, entry_count)

@router.post("/{event_id}/join")
@router.post("/{event_id}/enter")
async def enter_drop(
    event_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    fraud_guard: tuple[RiskLevel, list[str]] = Depends(anti_bot_farm)
):
    client_ip = get_client_ip(request)
    risk_level, risk_signals = fraud_guard

    # 1. Multi-Dimensional Rate Limiting (IP, User, Event+User, Event+IP)
    await check_multi_dim_rate_limits(
        request=request,
        scope="join",
        ip=client_ip,
        user_id=str(user.id),
        event_id=event_id
    )

    # 2. Concurrency-Safe Event Lock & Verification (Fix TOCTOU Race Condition)
    # Using with_for_update prevents concurrent admin closure/draw from racing with active registrations
    event = await db.scalar(
        select(Event).where(Event.id == event_id).with_for_update(read=True)
    )
    if not event or not event.is_open:
        raise HTTPException(status_code=400, detail="Event is not active or does not exist")

    now = datetime.now(timezone.utc)
    event_date = utc_time(event.event_date) if event.event_date else None
    registration_deadline = utc_time(event.registration_deadline) if event.registration_deadline else None

    if event_date and registration_deadline and registration_deadline >= event_date:
        raise HTTPException(status_code=400, detail="Registration deadline must be before the event date.")
    if event_date and now >= event_date:
        raise HTTPException(status_code=400, detail="Registration is closed because the event has started")
    if registration_deadline and now > registration_deadline:
        raise HTTPException(status_code=400, detail="Registration deadline has passed")

    # 3. High-Demand Event & Risk-based Phone Verification Requirement (Phase 5)
    is_high_demand = getattr(event, "requires_phone_verification", False)
    if (is_high_demand or risk_level == RiskLevel.HIGH) and not user.is_phone_verified:
        raise HTTPException(
            status_code=403,
            detail="Phone verification is required to join this high-demand event."
        )

    # 4. Atomic Idempotent Insert with ON CONFLICT DO NOTHING (Phase 3)
    # Never updates joined_at if entry already exists
    stmt = (
        insert(Entry)
        .values(event_id=event.id, user_id=user.id, status="ELIGIBLE")
        .on_conflict_do_nothing(index_elements=["event_id", "user_id"])
        .returning(Entry)
    )
    result = await db.execute(stmt)
    entry = result.scalar_one_or_none()
    
    if not entry:
        # ON CONFLICT was triggered: fetch existing entry without altering joined_at
        existing_result = await db.execute(
            select(Entry).where(Entry.event_id == event.id, Entry.user_id == user.id)
        )
        entry = existing_result.scalar_one()

    await db.commit()
    await db.refresh(entry)

    return {
        "entry_id": str(entry.id),
        "status": entry.allocation_status or entry.status,
        "joined_at": entry.joined_at,
        "batch_id": entry.batch_id,
    }

@router.get("/{event_id}/queue-status")
@router.get("/{event_id}/status")
async def get_my_status(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Frontend TanStack Query polls this every 5 seconds.
    It checks Allocations first (post-draw), then falls back to Entry (pre-draw).
    """
    entry_query = select(Entry).where(
        Entry.event_id == event_id,
        Entry.user_id == user.id,
    )
    entry = await db.scalar(entry_query)
    if not entry:
        raise HTTPException(status_code=404, detail="Not entered in this drop")

    alloc_query = select(Allocation).where(
        Allocation.event_id == event_id, 
        Allocation.user_id == user.id
    )
    alloc_result = await db.execute(alloc_query)
    allocation = alloc_result.scalar_one_or_none()

    if allocation:
        return {
            "status": allocation.status,
            "rank": allocation.rank,
            "claim_expires_at": allocation.claim_expires_at,
            "joined_at": entry.joined_at,
            "batch_id": entry.batch_id,
            "randomized_position": entry.randomized_position,
        }

    return {
        "status": entry.allocation_status or entry.status,
        "joined_at": entry.joined_at,
        "batch_id": entry.batch_id,
        "randomized_position": entry.randomized_position,
    }

@router.get("/{event_id}/audit")
async def get_audit_proof(event_id: str, db: AsyncSession = Depends(get_db)):
    """
    Public endpoint to prove the draw was fair.
    Phase 13: Permanent storage in PostgreSQL fallback if Redis is cleared.
    """
    data = await redis_client.get(f"audit:{event_id}")
    if data:
        return json.loads(data)

    # Redis cache miss: Query permanent audit record from PostgreSQL
    try:
        ev_uuid = uuid.UUID(event_id)
        run = await db.scalar(select(AllocationRun).where(AllocationRun.event_id == ev_uuid))
        if run and run.status == "COMPLETED" and run.result_json:
            audit_result = json.loads(run.result_json)
            # Re-populate Redis cache
            await redis_client.set(f"audit:{event_id}", run.result_json)
            return audit_result
    except Exception:
        pass

    raise HTTPException(status_code=404, detail="Draw has not happened yet")

@router.post("/{event_id}/claim")
async def claim_ticket(
    event_id: str,
    request: Request,
    idem_key: str = Header(..., alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    client_ip = get_client_ip(request)

    # 1. Rate limit claim attempts by IP and User
    await check_token_bucket(f"rl:claim:ip:{client_ip}", settings.RATE_LIMIT_CLAIM_CAPACITY, settings.RATE_LIMIT_CLAIM_REFILL)
    await check_token_bucket(f"rl:claim:user:{user.id}", settings.RATE_LIMIT_CLAIM_CAPACITY, settings.RATE_LIMIT_CLAIM_REFILL)

    # 2. Check Idempotency Cache
    cached = await redis_client.get(f"idem:{idem_key}")
    if cached:
        return json.loads(cached)

    try:
        # 3. Lock Allocation row for update
        alloc_query = select(Allocation).where(
            Allocation.event_id == event_id,
            Allocation.user_id == user.id
        ).with_for_update()

        alloc_result = await db.execute(alloc_query)
        alloc = alloc_result.scalar_one_or_none()

        if not alloc:
            raise HTTPException(404, "Allocation not found")
        if alloc.status == "RESERVED":
            raise HTTPException(400, "Ticket already claimed")
        if alloc.status != "WINNER":
            raise HTTPException(409, "Not eligible to claim a ticket")
            
        # Ensure timezone-aware comparison against authoritative backend clock
        now_utc = datetime.now(timezone.utc)
        if alloc.claim_expires_at and alloc.claim_expires_at < now_utc:
            raise HTTPException(409, "Claim window has expired")

        # 4. Lock the Event Row
        event_query = select(Event).where(Event.id == event_id).with_for_update()
        event_result = await db.execute(event_query)
        ev = event_result.scalar_one()

        if ev.remaining_seats <= 0:
            raise HTTPException(409, "Sold out")

        # 5. Execute Atomic Swap
        ev.remaining_seats -= 1
        alloc.status = "RESERVED"
        
        seat_number = ev.capacity - ev.remaining_seats

        res = Reservation(
            event_id=ev.id,
            user_id=user.id,
            allocation_id=alloc.id,
            seat_number=seat_number,
            idempotency_key=idem_key
        )
        db.add(res)
        
        # 6. Commit transaction, releasing PostgreSQL row locks
        await db.commit()
        await db.refresh(res)
        
        response_data = {
            "reservation_id": str(res.id),
            "seat_number": res.seat_number,
            "status": "RESERVED"
        }
        
        # Cache successful response in Redis for 24 hours
        await redis_client.setex(f"idem:{idem_key}", 86400, json.dumps(response_data))
        
        return response_data
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail="An error occurred while processing your request. Please try again.")
