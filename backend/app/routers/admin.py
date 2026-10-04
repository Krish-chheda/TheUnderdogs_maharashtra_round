import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select, asc
from app.core.database import get_db
from app.models.base import Event, User, Entry, Allocation, Reservation
from app.dependencies.auth import get_current_admin
from app.dependencies.rate_limit import check_token_bucket, get_client_ip
from app.services.allocation import allocate_event, commit_allocation
from app.core.redis import redis_client
from fastapi import BackgroundTasks, status
import sys
import asyncio
import json
from pathlib import Path
from app.core.redis import set_bot_test_progress, get_bot_test_progress
from pydantic import BaseModel, model_validator

router = APIRouter(prefix="/admin/events", tags=["admin"])

class EventCreate(BaseModel):
    name: str
    capacity: int
    venue: str
    event_date: datetime
    registration_deadline: datetime
    batch_duration_seconds: int = 120
    batch_weights: list[float] | None = None
    requires_phone_verification: bool = False

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
        if self.batch_duration_seconds <= 0:
            raise ValueError("Batch duration must be greater than zero.")
        if self.batch_weights is not None and (not self.batch_weights or any(weight <= 0 for weight in self.batch_weights)):
            raise ValueError("Batch weights must contain positive values.")
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
        batch_duration_seconds=event_data.batch_duration_seconds,
        batch_weights=event_data.batch_weights,
        capacity=event_data.capacity,
        remaining_seats=event_data.capacity,
        requires_phone_verification=event_data.requires_phone_verification,
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

@router.post("/{event_id}/allocation/commit")
async def commit_event_allocation(
    event_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """
    Phase 11: Create pre-draw commitment before executing allocation.
    """
    client_ip = get_client_ip(request)
    await check_token_bucket(f"rl:admin_alloc:{client_ip}", capacity=20, refill=2.0)
    try:
        return await commit_allocation(db, event_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

@router.post("/{event_id}/allocation/run")
@router.post("/{event_id}/allocate")
async def run_allocation(
    event_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """
    Execute allocation draw using pre-committed seed (or auto-commit if not yet committed).
    """
    client_ip = get_client_ip(request)
    await check_token_bucket(f"rl:admin_alloc:{client_ip}", capacity=20, refill=2.0)
    try:
        return await allocate_event(db, event_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

@router.post("/{event_id}/sweep")
async def sweep_waitlist(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
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

# ---------------------------------------------------------------------------
# Bot‑testing endpoints (admin only)
# ---------------------------------------------------------------------------

VALID_BOT_TESTS = {
    "high-speed-bot": "high-speed-bot",
    "high-volume-bot": "high-volume-bot",
    "duplicate-attack": "duplicate-attack",
    "flash-crowd": "flash-crowd",
}

class BotTestStartRequest(BaseModel):
    test_name: str

@router.post("/{event_id}/bot-test/start")
async def start_bot_test(
    event_id: uuid.UUID,
    request: BotTestStartRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
    background_tasks: BackgroundTasks = None,
):
    """Start a bot‑testing run for *event_id* and return a test identifier."""
    if request.test_name not in VALID_BOT_TESTS:
        raise HTTPException(status_code=400, detail="Invalid test_name")

    test_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    await set_bot_test_progress(test_id, {
        "test_id": test_id,
        "event_id": str(event_id),
        "status": "running",
        "started_at": now,
        "test_name": request.test_name,
        "log": "",
    })

    load_test_path = Path(__file__).resolve().parents[2] / "tests" / "load_test.py"
    if not load_test_path.is_file():
        raise HTTPException(status_code=500, detail="load_test script not found")

    async def _run():
        cmd = [sys.executable, str(load_test_path), "--scenario", request.test_name]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_chunks = []
        stderr_chunks = []
        async for line in proc.stdout:
            decoded = line.decode(errors="replace")
            stdout_chunks.append(decoded)
            await set_bot_test_progress(test_id, {"progress": decoded.strip()})
        async for line in proc.stderr:
            decoded = line.decode(errors="replace")
            stderr_chunks.append(decoded)
        await proc.wait()
        finished = datetime.now(timezone.utc)
        log = "".join(stdout_chunks) + "\n" + "".join(stderr_chunks)
        result_json = None
        error = None
        if proc.returncode == 0:
            reports = sorted(load_test_path.parent.glob("load_report_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            if reports:
                try:
                    result_json = json.loads(reports[0].read_text(encoding="utf-8"))
                except Exception as exc:
                    error = f"Failed to parse report: {exc}"
        else:
            error = f"Subprocess exited with code {proc.returncode}"

        await set_bot_test_progress(test_id, {
            "status": "completed" if proc.returncode == 0 and not error else "failed",
            "finished_at": finished,
            "log": log,
            "result_json": result_json or {},
            "error": error,
        })

    if background_tasks is None:
        background_tasks = BackgroundTasks()
    background_tasks.add_task(_run)
    return {"test_id": test_id, "status": "started"}

@router.get("/{event_id}/bot-test/{test_id}")
async def get_bot_test_status(
    event_id: uuid.UUID,
    test_id: str,
    _: User = Depends(get_current_admin),
):
    """Retrieve status and result of a bot‑test run."""
    data = await get_bot_test_progress(test_id)
    if not data:
        raise HTTPException(status_code=404, detail="Test not found")
    if data.get("event_id") != str(event_id):
        raise HTTPException(status_code=404, detail="Test not found for this event")
    return {
        "test_id": test_id,
        "event_id": data.get("event_id"),
        "status": data.get("status", "unknown"),
        "started_at": data.get("started_at"),
        "finished_at": data.get("finished_at"),
        "progress": data.get("progress"),
        "result": data.get("result_json"),
        "error": data.get("error"),
    }