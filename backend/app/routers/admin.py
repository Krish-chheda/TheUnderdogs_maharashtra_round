import hashlib
import secrets
import random
import json
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select, asc
from sqlalchemy.dialects.postgresql import insert
from app.core.database import get_db
from app.models.base import Event, User
from app.dependencies.auth import get_current_admin
from app.core.redis import redis_client
from app.models.base import Event, Entry, Allocation, Reservation
from pydantic import BaseModel, model_validator

router = APIRouter(prefix="/admin/events", tags=["admin"])

class EventCreate(BaseModel):
    name: str
    capacity: int
    venue: str
    event_date: datetime
    registration_deadline: datetime

    @model_validator(mode="after")
    def validate_schedule(self):
        event_date = self.event_date
        deadline = self.registration_deadline
        if event_date.tzinfo is None:
            event_date = event_date.replace(tzinfo=timezone.utc)
        else:
            event_date = event_date.astimezone(timezone.utc)
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        else:
            deadline = deadline.astimezone(timezone.utc)
        if deadline >= event_date:
            raise ValueError("Registration deadline must be before the event date.")
        return self

@router.post("/")
async def create_event(
    event_data: EventCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    new_event = Event(
        name=event_data.name,
        venue=event_data.venue,
        event_date=event_data.event_date,
        registration_deadline=event_data.registration_deadline,
        capacity=event_data.capacity,
        remaining_seats=event_data.capacity,
        is_open=True
    )
    db.add(new_event)
    await db.commit()
    await db.refresh(new_event)
    
    return {"event_id": str(new_event.id), "name": new_event.name}

@router.delete("/{event_id}")
async def delete_event(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    event = await db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    await db.execute(delete(Reservation).where(Reservation.event_id == event_id))
    await db.execute(delete(Allocation).where(Allocation.event_id == event_id))
    await db.execute(delete(Entry).where(Entry.event_id == event_id))
    await db.delete(event)
    await db.commit()
    await redis_client.delete(f"audit:{event_id}")

    return {"message": "Event deleted", "event_id": str(event_id)}


@router.post("/{event_id}/allocate")
async def run_allocation(event_id: str, db: AsyncSession = Depends(get_db)):
    # 1. Lock and close the event
    event = await db.get(Event, event_id)
    if not event or not event.is_open:
        raise HTTPException(400, "Event is already closed or does not exist")
        
    event.is_open = False
    await db.commit()
    
    # 2. Fetch all entries
    result = await db.execute(select(Entry).where(Entry.event_id == event_id, Entry.status == "ELIGIBLE"))
    entries = result.scalars().all()
    
    if not entries:
        return {"message": "No entries to allocate"}
        
    # 3. Deterministic Shuffle Engine
    # Sort entries by ID first so the input list is perfectly consistent
    sorted_entries = sorted(entries, key=lambda e: str(e.id))
    list_string = "".join(str(e.id) for e in sorted_entries)
    list_hash = hashlib.sha256(list_string.encode()).hexdigest()
    
    # Generate the unguessable seed and its public commitment
    seed_bytes = secrets.token_bytes(32)
    seed_hex = seed_bytes.hex()
    seed_commitment = hashlib.sha256(seed_bytes).hexdigest()
    
    # Seed the RNG combining the secret seed and the list state
    rng_seed = int.from_bytes(hashlib.sha256(seed_bytes + list_hash.encode()).digest(), "big")
    rng = random.Random(rng_seed)
    
    shuffled = sorted_entries[:]
    rng.shuffle(shuffled)
    
    capacity = event.capacity
    winners = shuffled[:capacity]
    waitlist = shuffled[capacity:]
    
    # 4. Bulk Insert Allocations
    allocations = []
    # Give winners a 10-minute window to claim their ticket
    claim_deadline = datetime.now(timezone.utc) + timedelta(minutes=10) 
    
    for rank, entry in enumerate(winners, start=1):
        allocations.append({
            "event_id": event.id,
            "user_id": entry.user_id,
            "rank": rank,
            "status": "WINNER",
            "claim_expires_at": claim_deadline
        })
        
    for rank, entry in enumerate(waitlist, start=len(winners) + 1):
        allocations.append({
            "event_id": event.id,
            "user_id": entry.user_id,
            "rank": rank,
            "status": "WAITLISTED",
            "claim_expires_at": None
        })
        
    if allocations:
        await db.execute(insert(Allocation).values(allocations))
        
    # 5. Store Audit Proof in Redis
    audit_data = {
        "list_hash": list_hash,
        "seed_commitment": seed_commitment,
        "seed": seed_hex 
    }
    await redis_client.set(f"audit:{event_id}", json.dumps(audit_data))
    
    await db.commit()
    
    return {
        "status": "ALLOCATION_COMPLETE",
        "winners": len(winners),
        "waitlisted": len(waitlist),
        "audit": audit_data
    }


@router.post("/{event_id}/sweep")
async def sweep_waitlist(event_id: str, db: AsyncSession = Depends(get_db)):
    now_utc = datetime.now(timezone.utc)
    
    # 1. Find and lock expired winners using SKIP LOCKED
    expired_query = select(Allocation).where(
        Allocation.event_id == event_id,
        Allocation.status == "WINNER",
        Allocation.claim_expires_at < now_utc
    ).with_for_update(skip_locked=True)
    
    result = await db.execute(expired_query)
    expired_allocations = result.scalars().all()
    
    if not expired_allocations:
        return {"message": "No expired tickets to sweep."}
        
    for alloc in expired_allocations:
        alloc.status = "EXPIRED"
        
    # 2. Promote waitlisted users based on rank
    spots_to_fill = len(expired_allocations)
    
    waitlist_query = select(Allocation).where(
        Allocation.event_id == event_id,
        Allocation.status == "WAITLISTED"
    ).order_by(asc(Allocation.rank)).limit(spots_to_fill).with_for_update(skip_locked=True)
    
    wl_result = await db.execute(waitlist_query)
    promoted_allocations = wl_result.scalars().all()
    
    # Give promoted users 10 minutes to claim
    claim_deadline = now_utc + timedelta(minutes=10)
    
    for alloc in promoted_allocations:
        alloc.status = "WINNER"
        alloc.claim_expires_at = claim_deadline
        
    await db.commit()
    
    return {
        "status": "SWEEP_COMPLETE",
        "revoked_tickets": spots_to_fill,
        "promoted_users": len(promoted_allocations)
    }