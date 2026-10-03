# Fair Drop API Specification

**Generated:** 2026-10-04  
**Backend:** FastAPI (Python)  
**Database:** PostgreSQL (async via asyncpg)  
**Cache:** Redis  
**Authentication:** JWT Bearer Token (HS256)

---

## Table of Contents

1. [Authentication & Security](#authentication--security)
2. [Core Concepts](#core-concepts)
3. [Rate Limiting](#rate-limiting)
4. [Authentication Routes](#authentication-routes)
5. [Events Routes](#events-routes)
6. [Admin Routes](#admin-routes)
7. [Data Models](#data-models)
8. [Error Handling](#error-handling)
9. [Enums & Constants](#enums--constants)
10. [Special Endpoints](#special-endpoints)
11. [Examples](#examples)

---

## Authentication & Security

### JWT Bearer Token
- **Algorithm:** HS256
- **Secret:** `JWT_SECRET` environment variable (min 32 chars in production)
- **Token Expiry:** 24 hours (configurable: `ACCESS_TOKEN_EXPIRE_MINUTES`)
- **Header:** `Authorization: Bearer <token>`
- **Scheme:** HTTP Bearer

### Token Payload
```json
{
  "sub": "<user_id>",
  "role": "user|admin",
  "exp": <unix_timestamp>
}
```

### Authentication Dependency
- **`get_current_user`:** Validates Bearer token, returns authenticated User
- **`get_current_admin`:** Extends `get_current_user`, requires `role="admin"`
- **Failure Response:** 401 Unauthorized with `WWW-Authenticate: Bearer` header

### Password Security
- **Hashing:** bcrypt with auto-generated salt
- **Verification:** Constant-time comparison (bcrypt.checkpw)
- **Requirements:** 8-72 characters

### OTP Security
- **Generation:** Cryptographically secure 6-digit code (secrets.choice)
- **Storage:** Salted SHA-256 hash in Redis (no plaintext)
- **Verification:** HMAC constant-time comparison
- **Expiry:** Configurable (default: 300 seconds / 5 minutes)
- **Max Attempts:** 5 (configurable)
- **One-Time Use:** OTP deleted after successful verification

---

## Core Concepts

### Event States
- **Open:** Registration deadline not passed, event not started
- **Closed:** Registration deadline passed or event started
- **Completed:** Event date has passed
- **Invalid Schedule:** Registration deadline >= event date

### Allocation Phases
1. **Registration Phase:** Users join events (Entry records created)
2. **Commitment Phase:** Admin calls `/allocation/commit` → generates seed, locks event
3. **Draw Phase:** Admin calls `/allocation/run` → executes draw, creates Allocation records
4. **Claim Phase:** Winners claim tickets within 24-hour window
5. **Sweep Phase:** Expired winners' tickets reassigned to waitlisted users

### Batch System
- Entries grouped by registration time (batch_duration_seconds, default: 120s)
- Each batch allocated quota based on batch_weights
- Default weights: [0.30, 0.25, 0.20, 0.15, 0.10] (normalized)
- Randomization: HMAC-SHA256 seeded ordering within each batch

### Fairness Guarantees
- **Two-Phase Commit:** Seed commitment + reveal prevents admin manipulation
- **Audit Trail:** Deterministic JSON hash + permanent PostgreSQL storage
- **Race Condition Prevention:** 
  - `with_for_update()` on Event and Allocation rows
  - Idempotency keys for claim operations
  - Atomic INSERT with ON CONFLICT DO NOTHING for entries

---

## Rate Limiting

### Implementation
- **Algorithm:** Token Bucket (Lua script in Redis)
- **Header:** `Retry-After` (seconds) when limit exceeded
- **Response:** 429 Too Many Requests

### Rate Limit Configurations

| Scope | Dimension | Capacity | Refill (tokens/sec) | Use Case |
|-------|-----------|----------|---------------------|----------|
| **Join** | IP | 20 | 2.0 | Per-IP entry attempts |
| **Join** | User | 5 | 0.5 | Per-user entry attempts |
| **Join** | Event + User | 3 | 0.2 | Per-event per-user entries |
| **Join** | Event + IP | 30 | 3.0 | Per-event per-IP entries |
| **OTP Send** | IP | 3 | 0.05 (1 per 20s) | OTP request rate |
| **OTP Send** | Phone | 3 | 0.05 | Per-phone OTP requests |
| **OTP Verify** | IP | 5 | 0.1 | OTP verification attempts |
| **OTP Verify** | Phone | 5 | 0.1 | Per-phone verification attempts |
| **Login** | IP | 10 | 0.5 | Login attempt rate |
| **Login** | Email | 10 | 0.5 | Per-email login rate |
| **Claim** | IP | 5 | 0.5 | Ticket claim rate |
| **Claim** | User | 5 | 0.5 | Per-user claim rate |
| **Admin Allocation** | IP | 20 | 2.0 | Admin allocation operations |

### Multi-Dimensional Rate Limiting
When a user performs an action (e.g., join event), these checks execute in order:
1. IP dimension
2. Event + IP dimension
3. User dimension
4. Event + User dimension

All must pass for request to proceed.

---

## Authentication Routes

### Base Path
`/auth`

---

### POST /auth/signup
Create a new user account.

**Authentication:** None (public)

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "securepassword123",
  "role": "user"
}
```

**Request Schema (Pydantic):**
```python
class SignupRequest(BaseModel):
    email: str
    password: str = Field(..., min_length=8, max_length=72)
    role: str = "user"  # "user" or "admin"
```

**Response (201 Created):**
```json
{
  "message": "Account created",
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "role": "user"
}
```

**Error Responses:**
- `400 Bad Request` - Invalid role (not "user" or "admin")
- `409 Conflict` - Email already exists
- `429 Too Many Requests` - Signup rate limit exceeded (10 per 2 req/sec per IP)

**Rate Limits:**
- IP: 10 capacity, 0.5 tokens/sec refill

---

### POST /auth/login
Authenticate with email and password.

**Authentication:** None (public)

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "securepassword123"
}
```

**Request Schema:**
```python
class AuthCredentials(BaseModel):
    email: str
    password: str = Field(..., min_length=8, max_length=72)
```

**Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "role": "user",
  "is_phone_verified": false
}
```

**Error Responses:**
- `401 Unauthorized` - Invalid email or password
- `429 Too Many Requests` - Rate limited (IP or email)

**Rate Limits:**
- IP: 10 capacity, 0.5 tokens/sec
- Email: 10 capacity, 0.5 tokens/sec

---

### POST /auth/otp
Request a one-time password for phone verification.

**Authentication:** None (public)

**Request Body:**
```json
{
  "phone": "9876543210"
}
```

**Request Schema:**
```python
class OTPRequest(BaseModel):
    phone: str = Field(..., pattern=r"^\d{10}$", description="Must be exactly 10 digits")
```

**Response (200 OK):**
```json
{
  "message": "OTP sent"
}
```

**Behavior (Development Only):**
- In non-production environments, OTP is logged to console for testing
- Format: `[DEV ONLY SMS SIMULATION] Phone: 9876543210 | OTP: 123456`

**Error Responses:**
- `422 Unprocessable Entity` - Invalid phone format (not 10 digits)
- `429 Too Many Requests` - Rate limited

**Rate Limits:**
- IP: 3 capacity, 0.05 tokens/sec (1 per 20 seconds)
- Phone: 3 capacity, 0.05 tokens/sec

**Storage:**
- Redis key: `otp:{phone}`
- TTL: `OTP_EXPIRE_SECONDS` (default: 300 seconds)
- Data structure: Hash with `hash`, `salt`, `attempts`, `created_at`

---

### POST /auth/verify
Verify OTP and obtain or link phone to account.

**Authentication:** None (public), but Bearer token accepted for linking

**Request Body:**
```json
{
  "phone": "9876543210",
  "code": "123456"
}
```

**Request Schema:**
```python
class OTPVerify(BaseModel):
    phone: str = Field(..., pattern=r"^\d{10}$")
    code: str = Field(..., min_length=6, max_length=6)
```

**Response (200 OK):**

**Scenario 1: Authenticated user (Bearer token provided)**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "phone_verified": true,
  "message": "Phone successfully verified and linked."
}
```

**Scenario 2: Unauthenticated (phone-based signup)**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "phone_verified": true
}
```

**Error Responses:**
- `400 Bad Request` - OTP expired, invalid code, or max attempts exceeded
- `429 Too Many Requests` - Rate limited or extreme bot velocity detected

**Rate Limits:**
- IP: 5 capacity, 0.1 tokens/sec
- Phone: 5 capacity, 0.1 tokens/sec

**Side Effects:**
- Updates User: `phone`, `is_phone_verified`, `phone_verified_at`
- Creates User if phone-based signup and user doesn't exist
- Deletes OTP from Redis after successful verification
- New user created with email format: `{phone}@otp.local`

---

## Events Routes

### Base Path
`/events`

---

### GET /events
List all events with entry counts.

**Authentication:** None (public)

**Query Parameters:** None

**Response (200 OK):**
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Summer Concert",
    "description": "Fair Drop allocation event.",
    "date": "2026-10-15T18:00:00+00:00",
    "timezone": "UTC",
    "registrationDeadline": "2026-10-14T18:00:00+00:00",
    "capacity": 100,
    "entryCount": 250,
    "status": "Open",
    "venue": "Central Park",
    "isOpen": true,
    "scheduleValid": true,
    "scheduleError": null,
    "requiresPhoneVerification": false
  }
]
```

**Response Schema:**
```python
class EventList(BaseModel):
    id: str (UUID)
    name: str
    description: str
    date: str | null (ISO 8601)
    timezone: str
    registrationDeadline: str | null (ISO 8601)
    capacity: int
    entryCount: int
    status: str  # "Open", "Closed", "Completed", "Invalid schedule"
    venue: str
    isOpen: bool
    scheduleValid: bool
    scheduleError: str | null
    requiresPhoneVerification: bool
```

---

### GET /events/{event_id}
Get details of a single event.

**Authentication:** None (public)

**Path Parameters:**
- `event_id` (UUID): Event identifier

**Response (200 OK):** Same as GET /events item

**Error Responses:**
- `404 Not Found` - Event does not exist

---

### POST /events/{event_id}/join
### POST /events/{event_id}/enter
Join/enter an event (participate in the drop).

**Authentication:** Required (Bearer token)

**Path Parameters:**
- `event_id` (string/UUID): Event identifier

**Request Body:** (empty)

**Response (200 OK):**
```json
{
  "entry_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "ELIGIBLE",
  "joined_at": "2026-10-01T10:30:00+00:00",
  "batch_id": "batch-1",
  "randomized_position": null
}
```

**Error Responses:**
- `400 Bad Request` - Event not active, registration closed, or schedule invalid
- `403 Forbidden` - Phone verification required (high-demand event or HIGH risk level)
- `404 Not Found` - Entry not found after creation (shouldn't occur)
- `429 Too Many Requests` - Rate limited (multi-dimensional)

**Behavior:**
- Idempotent: If user already entered, returns existing entry without updating `joined_at`
- Creates Entry record with status="ELIGIBLE"
- Batch assignment occurs during allocation, not at join time
- Concurrency-safe: Uses `with_for_update(read=True)` on Event
- Risk-based phone verification: HIGH risk users or high-demand events require phone verification
- Triggers anti-bot farm assessment

**Rate Limits (Multi-Dimensional):**
1. IP: 20 capacity, 2.0 tokens/sec
2. Event + IP: 30 capacity, 3.0 tokens/sec
3. User: 5 capacity, 0.5 tokens/sec
4. Event + User: 3 capacity, 0.2 tokens/sec

**Schedule Validation:**
- Event must be open (`is_open=true`)
- If event_date and registration_deadline both set: deadline must be before event_date
- If event_date set: current time must be before event_date
- If registration_deadline set: current time must be before or equal to deadline

---

### GET /events/{event_id}/queue-status
### GET /events/{event_id}/status
Poll for user's current allocation status in event.

**Authentication:** Required (Bearer token)

**Path Parameters:**
- `event_id` (UUID): Event identifier

**Response (200 OK):**

**Scenario 1: Post-allocation (Allocation record exists)**
```json
{
  "status": "WINNER",
  "rank": 5,
  "claim_expires_at": "2026-10-02T10:30:00+00:00",
  "joined_at": "2026-10-01T10:30:00+00:00",
  "batch_id": "batch-1",
  "randomized_position": 1
}
```

**Scenario 2: Pre-allocation (Entry record only)**
```json
{
  "status": "ELIGIBLE",
  "joined_at": "2026-10-01T10:30:00+00:00",
  "batch_id": null,
  "randomized_position": null
}
```

**Response Schema:**
```python
class StatusResponse(BaseModel):
    status: str  # "ELIGIBLE", "WINNER", "WAITLISTED", "EXPIRED", "RESERVED"
    rank: int | null  # Only if allocated
    claim_expires_at: datetime | null  # Only if WINNER
    joined_at: datetime
    batch_id: str | null
    randomized_position: int | null
```

**Error Responses:**
- `404 Not Found` - User not entered in this event

**Behavior:**
- Checks Allocation table first (post-draw)
- Falls back to Entry table (pre-draw)
- Polls every 5 seconds from frontend (TanStack Query)

---

### GET /events/{event_id}/audit
Get fair draw audit proof and allocation results.

**Authentication:** None (public)

**Path Parameters:**
- `event_id` (string/UUID): Event identifier

**Response (200 OK):**
```json
{
  "allocation_run_id": "550e8400-e29b-41d4-a716-446655440000",
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "capacity": 100,
  "eligible_entry_count": 250,
  "winner_count": 100,
  "waitlist_count": 150,
  "entry_list_hash": "a1b2c3d4e5f6...",
  "seed_commitment": "xyz789abc123...",
  "revealed_seed": "fedcba987654...",
  "allocation_result_hash": "123abc456def...",
  "status": "ALLOCATION_COMPLETE",
  "seed_verified": true,
  "commitment_created_at": "2026-10-01T11:00:00+00:00",
  "allocation_executed_at": "2026-10-01T11:15:00+00:00",
  "batch_definitions": [
    {
      "batch_id": "batch-1",
      "entry_count": 50,
      "quota": 30,
      "weight": 0.30
    }
  ],
  "winners_by_batch": {
    "batch-1": 30,
    "batch-2": 25,
    "batch-3": 20,
    "batch-4": 15,
    "batch-5": 10
  },
  "winners": 100,
  "waitlisted": 150
}
```

**Error Responses:**
- `404 Not Found` - Draw has not happened yet, or no audit record exists

**Storage:**
- Cached in Redis: `audit:{event_id}`
- Permanent storage in PostgreSQL: `AllocationRun.result_json`
- Falls back to PostgreSQL if Redis cache miss

---

### POST /events/{event_id}/claim
Claim a winning ticket (reserve a seat).

**Authentication:** Required (Bearer token)

**Path Parameters:**
- `event_id` (string/UUID): Event identifier

**Headers (Required):**
- `Idempotency-Key` (string): Unique request identifier (UUID recommended)

**Request Body:** (empty)

**Response (200 OK):**
```json
{
  "reservation_id": "550e8400-e29b-41d4-a716-446655440000",
  "seat_number": 42,
  "status": "RESERVED"
}
```

**Error Responses:**
- `400 Bad Request` - Allocation not found or already claimed
- `404 Not Found` - Allocation record missing
- `409 Conflict` - Not eligible (status != "WINNER"), claim window expired, or event sold out
- `429 Too Many Requests` - Rate limited
- `500 Server Error` - Processing error

**Behavior:**
- Requires status="WINNER" and within 24-hour claim window
- Atomic transaction: locks Allocation and Event rows for update
- Decrements `event.remaining_seats` and sets `allocation.status="RESERVED"`
- Creates Reservation record with idempotency_key
- Seat number calculated: `capacity - remaining_seats`
- Cached in Redis for idempotency: `idem:{idempotency_key}` (24-hour TTL)
- Concurrent claim attempts with same idempotency key return cached response

**Rate Limits:**
- IP: 5 capacity, 0.5 tokens/sec
- User: 5 capacity, 0.5 tokens/sec

---

## Admin Routes

### Base Path
`/admin/events`

---

### POST /admin/events/
Create a new event (admin only).

**Authentication:** Required (Bearer token with `role="admin"`)

**Request Body:**
```json
{
  "name": "Summer Concert 2026",
  "capacity": 100,
  "venue": "Central Park Amphitheater",
  "event_date": "2026-10-15T18:00:00Z",
  "registration_deadline": "2026-10-14T18:00:00Z",
  "batch_duration_seconds": 120,
  "batch_weights": [0.30, 0.25, 0.20, 0.15, 0.10],
  "requires_phone_verification": false
}
```

**Request Schema:**
```python
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
        # Registration deadline must be before event date
        # Batch duration must be > 0
        # Batch weights must be positive if provided
```

**Response (200 OK):**
```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Summer Concert 2026"
}
```

**Error Responses:**
- `400 Bad Request` - Invalid schema (deadline >= event_date, invalid batch settings)
- `403 Forbidden` - User is not admin

---

### DELETE /admin/events/{event_id}
Delete an event and all related records (admin only).

**Authentication:** Required (Bearer token with `role="admin"`)

**Path Parameters:**
- `event_id` (UUID): Event identifier

**Response (200 OK):**
```json
{
  "message": "Event deleted",
  "event_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Cascade Deletes:**
- Reservations for this event
- Allocations for this event
- Entries for this event
- Event record itself
- Redis audit cache: `audit:{event_id}`

**Error Responses:**
- `404 Not Found` - Event does not exist
- `403 Forbidden` - User is not admin

---

### POST /admin/events/{event_id}/allocation/commit
Create pre-draw commitment with cryptographic seed (Phase 11).

**Authentication:** Required (Bearer token with `role="admin"`)

**Path Parameters:**
- `event_id` (UUID): Event identifier

**Request Body:** (empty)

**Response (200 OK):**
```json
{
  "status": "COMMITTED",
  "allocation_run_id": "550e8400-e29b-41d4-a716-446655440000",
  "seed_commitment": "abc123def456...",
  "entry_list_hash": "xyz789abc123...",
  "commitment_created_at": "2026-10-01T11:00:00+00:00",
  "eligible_entry_count": 250,
  "batch_definitions": [
    {
      "batch_id": "batch-1",
      "entry_count": 50,
      "quota": 30,
      "weight": 0.30
    }
  ]
}
```

**Error Responses:**
- `400 Bad Request` - Event not found or already committed
- `403 Forbidden` - User is not admin
- `429 Too Many Requests` - Rate limited (20 capacity, 2.0 tokens/sec per IP)

**Behavior:**
- Generates cryptographically secure 32-byte seed (secrets.token_bytes)
- Computes SHA256 commitment hash (immutable)
- Closes event: sets `is_open=false`
- Groups entries by batch (based on batch_duration_seconds)
- Calculates winner quotas using batch weights
- Creates AllocationRun record in PostgreSQL with status="COMMITTED"
- Idempotent: Returns existing commitment if already committed

**AllocationRun Fields:**
- `allocation_seed`: Hex-encoded 32-byte seed
- `seed_commitment`: SHA256(seed)
- `revealed_seed`: null (until draw executed)
- `status`: "COMMITTED"
- `batch_definitions`: Array of batch metadata
- `entry_list_hash`: SHA256 hash of all eligible entry IDs
- `eligible_entry_count`: Count of ELIGIBLE entries
- `commitment_created_at`: Timestamp

---

### POST /admin/events/{event_id}/allocation/run
### POST /admin/events/{event_id}/allocate
Execute the allocation draw using pre-committed seed (Phase 12).

**Authentication:** Required (Bearer token with `role="admin"`)

**Path Parameters:**
- `event_id` (UUID): Event identifier

**Request Body:** (empty)

**Response (200 OK):**
```json
{
  "allocation_run_id": "550e8400-e29b-41d4-a716-446655440000",
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "capacity": 100,
  "eligible_entry_count": 250,
  "winner_count": 100,
  "waitlist_count": 150,
  "entry_list_hash": "a1b2c3d4e5f6...",
  "seed_commitment": "xyz789abc123...",
  "revealed_seed": "fedcba987654...",
  "allocation_result_hash": "123abc456def...",
  "status": "ALLOCATION_COMPLETE",
  "seed_verified": true,
  "commitment_created_at": "2026-10-01T11:00:00+00:00",
  "allocation_executed_at": "2026-10-01T11:15:00+00:00",
  "batch_definitions": [
    {
      "batch_id": "batch-1",
      "entry_count": 50,
      "quota": 30,
      "weight": 0.30
    }
  ],
  "winners_by_batch": {
    "batch-1": 30,
    "batch-2": 25,
    "batch-3": 20,
    "batch-4": 15,
    "batch-5": 10
  },
  "winners": 100,
  "waitlisted": 150
}
```

**Error Responses:**
- `400 Bad Request` - Registration must be closed first
- `403 Forbidden` - User is not admin
- `429 Too Many Requests` - Rate limited

**Behavior:**
- Auto-commits if allocation not yet committed
- Verifies seed matches commitment (assertion)
- Orders entries within each batch using HMAC-SHA256(seed, entry_id)
- Selects winners based on batch quotas
- Remaining entries marked as WAITLISTED
- Claims expire 24 hours from execution
- Creates Allocation records for all winners/waitlisted users
- Generates deterministic canonical JSON audit hash
- Stores complete audit in PostgreSQL and Redis
- Idempotent: Returns existing results if already completed

**Allocation Records:**
- `status`: "WINNER" or "WAITLISTED"
- `rank`: Sequential rank (1 = first chance)
- `claim_expires_at`: now + 24 hours (WINNER only)
- `allocation_run_id`: Reference to AllocationRun

**Rate Limits:**
- IP: 20 capacity, 2.0 tokens/sec

---

### POST /admin/events/{event_id}/sweep
Promote waitlisted users when winners' claims expire (Phase 14).

**Authentication:** Required (Bearer token with `role="admin"`)

**Path Parameters:**
- `event_id` (string/UUID): Event identifier

**Request Body:** (empty)

**Response (200 OK):**
```json
{
  "status": "SWEEP_COMPLETE",
  "revoked_tickets": 5,
  "promoted_users": 5
}
```

**Behavior:**
- Finds WINNER allocations where `claim_expires_at < now`
- Marks them as "EXPIRED"
- Promotes top N waitlisted users (by rank) to WINNER
- Gives promoted users 10-minute claim window
- Uses SKIP LOCKED for non-blocking row selection

**Locking:**
- Avoids deadlocks with concurrent claims
- Skips rows held by other transactions

---

## Data Models

### User
```python
class User(Base):
    __tablename__ = "users"
    
    id: UUID (primary key)
    phone: str | None (unique, indexed) # 10 digits or null
    email: str (unique, indexed)
    password_hash: str
    role: str (default: "user") # "user" or "admin"
    is_phone_verified: bool (default: False)
    phone_verified_at: datetime | None (timezone-aware)
    created_at: datetime (server default: now())
```

**Indexes:**
- `phone` (unique)
- `email` (unique)

---

### Event
```python
class Event(Base):
    __tablename__ = "events"
    
    id: UUID (primary key)
    name: str
    venue: str | None
    event_date: datetime | None (timezone-aware)
    registration_deadline: datetime | None (timezone-aware)
    registration_start: datetime | None (timezone-aware, server default: now())
    batch_duration_seconds: int (default: 120)
    batch_weights: list[float] | None (JSON)
    capacity: int
    remaining_seats: int
    is_open: bool (default: True)
    requires_phone_verification: bool (default: False)
    created_at: datetime (server default: now())
```

**Validation:**
- `registration_deadline` < `event_date` (if both set)
- `capacity` > 0
- `batch_duration_seconds` > 0

---

### Entry
```python
class Entry(Base):
    __tablename__ = "entries"
    
    id: UUID (primary key)
    event_id: UUID (foreign key to Event)
    user_id: UUID (foreign key to User)
    status: str (default: "ELIGIBLE") # "ELIGIBLE"
    joined_at: datetime (timezone-aware, server default: now())
    batch_id: str | None # "batch-1", "batch-2", etc.
    randomized_position: int | None # Position within batch after randomization
    allocation_status: str | None # "WINNER", "WAITLISTED", etc. (mirrors Allocation.status)
    allocated_at: datetime | None (timezone-aware)
    created_at: datetime (server default: now())
    
    UniqueConstraint: (event_id, user_id) # One entry per user per event
```

---

### AllocationRun
```python
class AllocationRun(Base):
    __tablename__ = "allocation_runs"
    
    id: UUID (primary key)
    event_id: UUID (unique foreign key to Event)
    allocation_seed: str # Hex-encoded 32-byte seed
    seed_commitment: str # SHA256(seed)
    revealed_seed: str | None # Seed hex after draw execution
    allocation_result_hash: str | None # SHA256 of canonical JSON
    commitment_created_at: datetime | None (timezone-aware)
    allocation_executed_at: datetime | None (timezone-aware)
    batch_duration_seconds: int
    allocation_policy: dict (JSON) # {"weights": [...], "redistribution": "deterministic_weight_order"}
    batch_definitions: list (JSON) # [{"batch_id": "...", "entry_count": ..., "quota": ..., "weight": ...}]
    entry_list_hash: str # SHA256 of concatenated entry IDs
    eligible_entry_count: int
    winner_count: int
    waitlist_count: int
    allocated_at: datetime (server default: now())
    status: str # "COMMITTED" or "COMPLETED"
    result_json: str # JSON with full audit trail
```

**Status Values:**
- `"COMMITTED"`: Seed locked, awaiting draw
- `"COMPLETED"`: Draw executed, allocations finalized

---

### Allocation
```python
class Allocation(Base):
    __tablename__ = "allocations"
    
    id: UUID (primary key)
    event_id: UUID (foreign key to Event)
    user_id: UUID (foreign key to User)
    rank: int # Position in allocation queue (1 = highest priority)
    status: str # "WINNER", "WAITLISTED", "EXPIRED", "RESERVED"
    claim_expires_at: datetime | None (timezone-aware) # 24 hours for WINNER
    allocation_run_id: UUID | None (foreign key to AllocationRun)
    
    UniqueConstraint: (event_id, user_id) # One allocation per user per event
    UniqueConstraint: (event_id, rank) # No two users share same rank
```

---

### Reservation
```python
class Reservation(Base):
    __tablename__ = "reservations"
    
    id: UUID (primary key)
    event_id: UUID (foreign key to Event)
    user_id: UUID (foreign key to User)
    allocation_id: UUID (unique foreign key to Allocation)
    seat_number: int # Assigned seat (1 to capacity)
    idempotency_key: str (unique)
    created_at: datetime (server default: now())
    
    UniqueConstraint: (event_id, user_id) # One reservation per user per event
    UniqueConstraint: (event_id, seat_number) # One user per seat
```

---

## Error Handling

### HTTP Status Codes

| Code | Meaning | Use Case |
|------|---------|----------|
| 200 | OK | Successful request |
| 201 | Created | Resource created (signup) |
| 400 | Bad Request | Invalid input, validation failure |
| 401 | Unauthorized | Missing/invalid JWT token |
| 403 | Forbidden | Insufficient permissions (admin), phone verification required |
| 404 | Not Found | Resource doesn't exist |
| 409 | Conflict | State conflict (already claimed, sold out) |
| 422 | Unprocessable Entity | Validation error (Pydantic) |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Server Error | Unexpected server error |

### Error Response Format
```json
{
  "detail": "Human-readable error message"
}
```

### Rate Limit Response
```json
{
  "detail": "Too many requests. Please slow down."
}
```

**Headers:**
- `Retry-After: <seconds>` - Calculated based on token bucket state

### Authentication Failure
```json
{
  "detail": "Could not validate credentials"
}
```

**Headers:**
- `WWW-Authenticate: Bearer`

---

## Enums & Constants

### User Roles
```python
Role = Literal["user", "admin"]
```

### Entry Status
```python
EntryStatus = Literal["ELIGIBLE"]
```

### Allocation Status
```python
AllocationStatus = Literal["WINNER", "WAITLISTED", "EXPIRED", "RESERVED"]
```

### Event Status
```python
EventStatus = Literal["Open", "Closed", "Completed", "Invalid schedule"]
```

### Risk Levels (Fraud Detection)
```python
class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
```

### AllocationRun Status
```python
AllocationRunStatus = Literal["COMMITTED", "COMPLETED"]
```

### Default Batch Weights
```python
DEFAULT_BATCH_WEIGHTS = [0.30, 0.25, 0.20, 0.15, 0.10]
```

### Timestamps
- All timestamps are **UTC timezone-aware**
- Format: ISO 8601 (RFC 3339)
- Example: `"2026-10-01T10:30:00+00:00"`

---

## Special Endpoints

### Audit Endpoint
**GET /events/{event_id}/audit** (public, no auth)

Provides verifiable proof that the draw was fair. Returns:
- Seed commitment (immutable hash)
- Revealed seed (post-draw)
- Entry list hash
- Winner/waitlist counts by batch
- Result hash (canonical JSON)

Uses dual storage for durability:
- Redis cache: Fast retrieval
- PostgreSQL: Permanent fallback

### Idempotency-Key Header
**POST /events/{event_id}/claim** requires:

```
Idempotency-Key: <UUID>
```

- Cached in Redis for 24 hours
- Prevents duplicate reservations on retry
- Enables safe client-side retries

### Two-Phase Allocation
**Phase 1: Commit**
- POST `/admin/events/{event_id}/allocation/commit`
- Locks seed, freezes entry list

**Phase 2: Execute**
- POST `/admin/events/{event_id}/allocation/run`
- Reveals seed, assigns winners/waitlist
- Generates audit proof

### Sweep Mechanism
**POST /admin/events/{event_id}/sweep** (admin only)

Automatically promotes waitlisted users when winners' claim windows expire:
- Finds WINNER allocations where `claim_expires_at < now`
- Marks as EXPIRED
- Promotes top waitlisted by rank to WINNER (10-min claim window)
- Non-blocking row selection (SKIP LOCKED)

---

## Examples

### Complete User Flow: OTP Signup → Join Event → Claim Ticket

#### Step 1: Request OTP
```bash
curl -X POST http://localhost:8000/auth/otp \
  -H "Content-Type: application/json" \
  -d '{"phone": "9876543210"}'
```

Response:
```json
{"message": "OTP sent"}
```

Console (dev mode): `[DEV ONLY SMS SIMULATION] Phone: 9876543210 | OTP: 123456`

#### Step 2: Verify OTP
```bash
curl -X POST http://localhost:8000/auth/verify \
  -H "Content-Type: application/json" \
  -d '{"phone": "9876543210", "code": "123456"}'
```

Response:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "phone_verified": true
}
```

#### Step 3: List Events
```bash
curl http://localhost:8000/events
```

Response:
```json
[
  {
    "id": "660e8400-e29b-41d4-a716-446655440000",
    "name": "Summer Concert",
    "status": "Open",
    "isOpen": true,
    ...
  }
]
```

#### Step 4: Join Event
```bash
curl -X POST http://localhost:8000/events/660e8400-e29b-41d4-a716-446655440000/join \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
  -H "Content-Type: application/json" \
  -d '{}'
```

Response:
```json
{
  "entry_id": "770e8400-e29b-41d4-a716-446655440000",
  "status": "ELIGIBLE",
  "joined_at": "2026-10-01T10:30:00+00:00",
  "batch_id": null,
  "randomized_position": null
}
```

#### Step 5: Poll for Status
```bash
# Repeat every 5 seconds
curl http://localhost:8000/events/660e8400-e29b-41d4-a716-446655440000/queue-status \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

Response (pre-draw):
```json
{
  "status": "ELIGIBLE",
  "joined_at": "2026-10-01T10:30:00+00:00",
  "batch_id": null,
  "randomized_position": null
}
```

#### Step 6: Admin Commits Allocation
```bash
curl -X POST http://localhost:8000/admin/events/660e8400-e29b-41d4-a716-446655440000/allocation/commit \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Response:
```json
{
  "status": "COMMITTED",
  "allocation_run_id": "880e8400-e29b-41d4-a716-446655440000",
  "seed_commitment": "abc123...",
  ...
}
```

#### Step 7: Admin Executes Draw
```bash
curl -X POST http://localhost:8000/admin/events/660e8400-e29b-41d4-a716-446655440000/allocation/run \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Response:
```json
{
  "status": "ALLOCATION_COMPLETE",
  "winner_count": 50,
  "waitlist_count": 200,
  ...
}
```

#### Step 8: User Polls and Gets Winner Status
```bash
curl http://localhost:8000/events/660e8400-e29b-41d4-a716-446655440000/queue-status \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

Response (post-draw, if winner):
```json
{
  "status": "WINNER",
  "rank": 5,
  "claim_expires_at": "2026-10-02T10:30:00+00:00",
  "joined_at": "2026-10-01T10:30:00+00:00",
  "batch_id": "batch-1",
  "randomized_position": 3
}
```

#### Step 9: Claim Ticket
```bash
curl -X POST http://localhost:8000/events/660e8400-e29b-41d4-a716-446655440000/claim \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
  -H "Idempotency-Key: 9976a9e1-6ec3-4db2-ba3a-e5a3e4b4e5c8" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Response:
```json
{
  "reservation_id": "990e8400-e29b-41d4-a716-446655440000",
  "seat_number": 42,
  "status": "RESERVED"
}
```

### Admin Flow: Create Event → Allocate → Sweep

#### Create Event
```bash
curl -X POST http://localhost:8000/admin/events/ \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "New Year Giveaway",
    "capacity": 50,
    "venue": "Online",
    "event_date": "2026-12-31T23:59:00Z",
    "registration_deadline": "2026-12-31T23:00:00Z",
    "batch_duration_seconds": 300,
    "batch_weights": [0.5, 0.3, 0.2],
    "requires_phone_verification": true
  }'
```

#### Get Audit Proof (Public)
```bash
curl http://localhost:8000/events/660e8400-e29b-41d4-a716-446655440000/audit
```

Response:
```json
{
  "status": "ALLOCATION_COMPLETE",
  "seed_verified": true,
  "revealed_seed": "fedcba987654...",
  "allocation_result_hash": "123abc456def...",
  ...
}
```

---

## Configuration

### Environment Variables

| Variable | Type | Default | Purpose |
|----------|------|---------|---------|
| `ENV` | str | "development" | Environment mode |
| `DATABASE_URL` | str | postgres://localhost/fairdrop | PostgreSQL connection |
| `REDIS_URL` | str | redis://localhost:6379/0 | Redis connection |
| `JWT_SECRET` | str | super-secret-key-... | JWT signing key (min 32 chars in prod) |
| `JWT_ALGORITHM` | str | HS256 | JWT algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | int | 1440 (24 hours) | Token lifetime |
| `RATE_LIMIT_JOIN_IP_CAPACITY` | int | 20 | IP rate limit capacity |
| `RATE_LIMIT_JOIN_IP_REFILL` | float | 2.0 | Tokens/sec refill |
| `RATE_LIMIT_JOIN_USER_CAPACITY` | int | 5 | User rate limit |
| `RATE_LIMIT_JOIN_USER_REFILL` | float | 0.5 | Tokens/sec |
| ... (see config.py for full list) | | | |
| `OTP_EXPIRE_SECONDS` | int | 300 | OTP validity |
| `OTP_MAX_ATTEMPTS` | int | 5 | OTP verification tries |
| `IP_ACCOUNT_THRESHOLD` | int | 5 | Bot farm detection threshold |
| `IP_ACCOUNT_WINDOW_SECONDS` | int | 3600 | Fraud window (1 hour) |

---

## CORS Configuration

**Allowed Origins:**
- `http://localhost:5173`
- `http://127.0.0.1:5173`

**Allowed Methods:** All (`*`)

**Allowed Headers:** All (`*`)

**Credentials:** True (cookies allowed)

---

## Version & Compatibility

- **Framework:** FastAPI 0.100+
- **Python:** 3.10+
- **Database:** PostgreSQL 12+ with asyncpg
- **Cache:** Redis 6.0+
- **JWT Library:** PyJWT with python-jose
- **Password Hashing:** bcrypt

---

## Security Considerations

1. **Password Reset:** Not yet implemented
2. **Token Refresh:** Use reauthentication (login again)
3. **Session Management:** Stateless JWT (no logout endpoint)
4. **HTTPS:** Required in production (handled by reverse proxy)
5. **CORS:** Restricted to localhost development URLs
6. **Rate Limiting:** Prevents brute force and bot farms
7. **OTP:** One-time use, salted hash storage
8. **Audit:** Permanent, cryptographically verified
9. **Concurrency:** Row-level locking prevents race conditions
10. **Idempotency:** Key-based caching for safe retries

---

**End of API Specification**
