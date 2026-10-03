import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import select

from app.models.base import Event, Entry, Allocation, User
from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.rate_limit import rate_limit  # (Code provided previously)

router = APIRouter(prefix="/events", tags=["events"])

@router.post("/{event_id}/enter")
async def enter_drop(
    event_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    rl = Depends(rate_limit("enter", capacity=5, refill=0.5))
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