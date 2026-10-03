import uuid
from datetime import datetime, timezone
import json

from fastapi import APIRouter, Depends, HTTPException, Request, Header

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import select

from app.models.base import Event, Entry, Allocation, User, Reservation

from app.core.database import get_db
from app.core.redis import redis_client

from app.dependencies.auth import get_current_user
from app.dependencies.fraud import anti_bot_farm
from app.dependencies.rate_limit import rate_limit 






router = APIRouter(prefix="/events", tags=["events"])

@router.post("/{event_id}/enter")
async def enter_drop(
    event_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    rl = Depends(rate_limit("enter", capacity=5, refill=0.5)),
    fraud_guard = Depends(anti_bot_farm)
):
    # 1. Verify Event Status
    event = await db.get(Event, event_id)
    if not event or not event.is_open:
        raise HTTPException(status_code=400, detail="Event is not active or does not exist")

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

    return {
        "entry_id": str(entry.id),
        "status": entry.status
    }

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
    # Check if the draw happened and we have an allocation
    alloc_query = select(Allocation).where(
        Allocation.event_id == event_id, 
        Allocation.user_id == user.id
    )
    alloc_result = await db.execute(alloc_query)
    allocation = alloc_result.scalar_one_or_none()

    if allocation:
        return {
            "status": allocation.status,  # WINNER, WAITLISTED, EXPIRED, RESERVED
            "rank": allocation.rank,
            "claim_expires_at": allocation.claim_expires_at
        }

    # If no allocation, check if they are entered
    entry_query = select(Entry).where(
        Entry.event_id == event_id, 
        Entry.user_id == user.id
    )
    entry_result = await db.execute(entry_query)
    entry = entry_result.scalar_one_or_none()

    if entry:
        return {"status": entry.status} # ELIGIBLE

    raise HTTPException(status_code=404, detail="Not entered in this drop")

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

