import hashlib
import secrets
import random
import json
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app.core.database import get_db
from app.core.redis import redis_client
from app.models.base import Event, Entry, Allocation


from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from app.core.database import get_db
from app.models.base import Event

router = APIRouter(prefix="/admin/events", tags=["admin"])

class EventCreate(BaseModel):
    name: str
    capacity: int

@router.post("/")
async def create_event(event_data: EventCreate, db: AsyncSession = Depends(get_db)):
    """Sprint Hack: Unprotected route just to seed an event for testing."""
    new_event = Event(
        name=event_data.name,
        capacity=event_data.capacity,
        remaining_seats=event_data.capacity,
        is_open=True
    )
    db.add(new_event)
    await db.commit()
    await db.refresh(new_event)
    
    return {"event_id": str(new_event.id), "name": new_event.name}


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