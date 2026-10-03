import uuid
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

class Event(Base):
    __tablename__ = "events"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    capacity: Mapped[int] = mapped_column(Integer)
    remaining_seats: Mapped[int] = mapped_column(Integer)
    is_open: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

class Entry(Base):
    __tablename__ = "entries"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(50), default="ELIGIBLE")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        # Prevents a user from entering the same event twice
        UniqueConstraint('event_id', 'user_id', name='uix_event_user_entry'),
    )

class Allocation(Base):
    __tablename__ = "allocations"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    rank: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(50)) # WINNER, WAITLISTED, EXPIRED, RESERVED
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # Prevents a user from receiving multiple allocations per event
        UniqueConstraint('event_id', 'user_id', name='uix_event_user_allocation'),
        # Ensures no two users get the same queue rank
        UniqueConstraint('event_id', 'rank', name='uix_event_rank_allocation'),
    )

class Reservation(Base):
    __tablename__ = "reservations"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    allocation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("allocations.id"), unique=True)
    seat_number: Mapped[int] = mapped_column(Integer)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        # Prevents a user from claiming more than one seat per event
        UniqueConstraint('event_id', 'user_id', name='uix_event_user_reservation'),
        # Hard DB-level protection against double-booking a single seat
        UniqueConstraint('event_id', 'seat_number', name='uix_event_seat_reservation'),
    )