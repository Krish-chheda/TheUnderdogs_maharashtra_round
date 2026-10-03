import uuid
from datetime import datetime
from sqlalchemy import JSON, Text, String, Integer, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, index=True, nullable=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="user", server_default="user")
    is_phone_verified: Mapped[bool] = mapped_column(default=False, server_default="false")
    phone_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

class Event(Base):
    __tablename__ = "events"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    venue: Mapped[str | None] = mapped_column(String(255), nullable=True)
    event_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    registration_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    registration_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    batch_duration_seconds: Mapped[int] = mapped_column(Integer, server_default="120", default=120)
    batch_weights: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    capacity: Mapped[int] = mapped_column(Integer)
    remaining_seats: Mapped[int] = mapped_column(Integer)
    is_open: Mapped[bool] = mapped_column(default=True)
    requires_phone_verification: Mapped[bool] = mapped_column(default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

class Entry(Base):
    __tablename__ = "entries"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(50), default="ELIGIBLE")
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    batch_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    randomized_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    allocation_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    allocated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        # Prevents a user from entering the same event twice
        UniqueConstraint('event_id', 'user_id', name='uix_event_user_entry'),
    )

class AllocationRun(Base):
    __tablename__ = "allocation_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id"), unique=True)
    allocation_seed: Mapped[str] = mapped_column(String(128))
    seed_commitment: Mapped[str] = mapped_column(String(128))
    revealed_seed: Mapped[str | None] = mapped_column(String(128), nullable=True)
    allocation_result_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    commitment_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    allocation_executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    batch_duration_seconds: Mapped[int] = mapped_column(Integer)
    allocation_policy: Mapped[dict] = mapped_column(JSON)
    batch_definitions: Mapped[list] = mapped_column(JSON)
    entry_list_hash: Mapped[str] = mapped_column(String(128))
    eligible_entry_count: Mapped[int] = mapped_column(Integer)
    winner_count: Mapped[int] = mapped_column(Integer)
    waitlist_count: Mapped[int] = mapped_column(Integer)
    allocated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String(50))
    result_json: Mapped[str] = mapped_column(Text, default="{}")

class Allocation(Base):
    __tablename__ = "allocations"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    rank: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(50)) # WINNER, WAITLISTED, EXPIRED, RESERVED
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    allocation_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("allocation_runs.id"), nullable=True)

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