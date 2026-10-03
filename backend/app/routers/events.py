import uuid
from datetime import datetime, timezone
import json

from fastapi import APIRouter, Depends, HTTPException, Request, Header

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import func, select
from app.models.base import Event, Entry, Allocation, User
from sqlalchemy import func,select
from app.models.base import Event, Entry, Allocation, User, Reservation
from app.core.database import get_db
from app.core.redis import redis_client

from app.dependencies.auth import get_current_user
from app.dependencies.fraud import anti_bot_farm
from app.dependencies.rate_limit import rate_limit 






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
    rl = Depends(rate_limit("enter", capacity=5, refill=0.5)),
    fraud_guard = Depends(anti_bot_farm)
):
    event = await db.get(Event, event_id)
    existing_entry = await db.scalar(
        select(Entry).where(Entry.event_id == event_id, Entry.user_id == user.id)
    )
    if existing_entry:
        return {
            "entry_id": str(existing_entry.id),
            "status": existing_entry.allocation_status or existing_entry.status,
            "joined_at": existing_entry.joined_at,
            "batch_id": existing_entry.batch_id,
        }

    # Verify event status before creating the first entry.
    now = datetime.now(timezone.utc)
    event_date = utc_time(event.event_date) if event and event.event_date else None
    registration_deadline = utc_time(event.registration_deadline) if event and event.registration_deadline else None
    if not event or not event.is_open:
        raise HTTPException(status_code=400, detail="Event is not active or does not exist")
    if event_date and registration_deadline and registration_deadline >= event_date:
        raise HTTPException(status_code=400, detail="Registration deadline must be before the event date.")
    if event_date and now >= event_date:
        raise HTTPException(status_code=400, detail="Registration is closed because the event has started")
    if registration_deadline and now > registration_deadline:
        raise HTTPException(status_code=400, detail="Registration deadline has passed")

    # 2. Idempotent Insert (Concurrency Safe)
    stmt = (
        insert(Entry)
        .values(event_id=event_id, user_id=user.id, status="ELIGIBLE")
        .on_conflict_do_nothing(index_elements=["event_id", "user_id"])
        .returning(Entry)
    )
    result = await db.execute(stmt)
    entry = result.scalar_one_or_none()
    
    # 3. Handle Duplicate
    if not entry:
        # If entry is None, it means the ON CONFLICT triggered and dropped the insert.
        query = select(Entry).where(Entry.event_id == event_id, Entry.user_id == user.id)
        existing_result = await db.execute(query)
        entry = existing_result.scalar_one()

    await db.commit()
    await db.refresh(entry)

    return {
        "entry_id": str(entry.id),
        "status": entry.status,
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
async def get_audit_proof(event_id: str):
    """Public endpoint to prove the draw was fair."""
    data = await redis_client.get(f"audit:{event_id}")
    if not data:
        raise HTTPException(status_code=404, detail="Draw has not happened yet")
        
    return json.loads(data)


@router.post("/{event_id}/claim")
async def claim_ticket(
    event_id:str,
    idem_key: str = Header(...,alias = "Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    user:User = Depends(get_current_user)
):
    cached = await redis_client.get(f"idem:{idem_key}")
    if cached:
        return json.loads(cached)

    try:
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
            
        # Ensure timezone-aware comparison
        now_utc = datetime.now(timezone.utc)
        if alloc.claim_expires_at and alloc.claim_expires_at < now_utc:
            raise HTTPException(409, "Claim window has expired")

        # 3. Lock the Event Row
        event_query = select(Event).where(Event.id == event_id).with_for_update()
        event_result = await db.execute(event_query)
        ev = event_result.scalar_one()

        if ev.remaining_seats <= 0:
            raise HTTPException(409, "Sold out")

        # 4. Execute the Atomic Swap
        ev.remaining_seats -= 1
        alloc.status = "RESERVED"
        
        # Determine a simple seat number based on capacity
        seat_number = ev.capacity - ev.remaining_seats

        res = Reservation(
            event_id=ev.id,
            user_id=user.id,
            allocation_id=alloc.id,
            seat_number=seat_number,
            idempotency_key=idem_key
        )
        db.add(res)
        
        # 5. Commit the transaction, releasing the Postgres locks
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
        raise HTTPException(500, f"An error occurred: {str(e)}")

