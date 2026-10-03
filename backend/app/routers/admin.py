from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from app.core.database import get_db
from app.models.base import Event, User
from app.dependencies.auth import get_current_admin

router = APIRouter(prefix="/admin/events", tags=["admin"])

class EventCreate(BaseModel):
    name: str
    capacity: int

@router.post("/")
async def create_event(
    event_data: EventCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
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