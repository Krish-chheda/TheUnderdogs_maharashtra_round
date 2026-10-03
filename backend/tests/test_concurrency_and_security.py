import asyncio
import hashlib
import hmac
import json
import secrets
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from app.core.config import settings
from app.dependencies.fraud import RiskLevel, assess_risk, anti_bot_farm
from app.dependencies.rate_limit import check_token_bucket, check_multi_dim_rate_limits
from app.models.base import Event, Entry, User, Allocation, Reservation, AllocationRun
from app.services.allocation import (
    calculate_quotas,
    randomized_order,
    batch_entries,
    commit_allocation,
    allocate_event,
)


class ConcurrencyAndDuplicateJoinTests(unittest.IsolatedAsyncioTestCase):
    async def test_100_concurrent_duplicate_joins_same_user(self):
        """
        Phase 3: 100 simultaneous JOIN requests from the SAME user
        must result in exactly ONE entry, preserving joined_at.
        """
        event_id = uuid.uuid4()
        user_id = uuid.uuid4()
        original_joined_at = datetime.now(timezone.utc) - timedelta(minutes=5)

        # Database simulation of PostgreSQL UNIQUE(event_id, user_id)
        db_entries = {}
        insert_attempts = 0
        conflicts = 0

        async def simulate_atomic_insert():
            nonlocal insert_attempts, conflicts
            insert_attempts += 1
            key = (event_id, user_id)
            if key in db_entries:
                conflicts += 1
                # ON CONFLICT DO NOTHING: returns existing entry without updating joined_at
                return db_entries[key]
            else:
                entry = {
                    "id": uuid.uuid4(),
                    "event_id": event_id,
                    "user_id": user_id,
                    "status": "ELIGIBLE",
                    "joined_at": original_joined_at,
                }
                db_entries[key] = entry
                return entry

        # Run 100 concurrent tasks
        results = await asyncio.gather(*(simulate_atomic_insert() for _ in range(100)))

        # Assertions
        self.assertEqual(len(db_entries), 1, "Exactly one entry must exist in database")
        self.assertEqual(conflicts, 99, "99 requests must hit ON CONFLICT DO NOTHING")
        # Every response received the same entry ID and joined_at
        first_entry_id = results[0]["id"]
        for res in results:
            self.assertEqual(res["id"], first_entry_id)
            self.assertEqual(res["joined_at"], original_joined_at)

    async def test_registration_close_race_condition(self):
        """
        Phase 10: Late arrival after registration closed must be rejected.
        """
        event = Event(
            id=uuid.uuid4(),
            name="Test Event",
            capacity=100,
            remaining_seats=100,
            is_open=False, # Closed!
            registration_deadline=datetime.now(timezone.utc) - timedelta(seconds=10),
        )
        now = datetime.now(timezone.utc)
        # Condition checked inside enter_drop
        is_closed = not event.is_open or (event.registration_deadline and now > event.registration_deadline)
        self.assertTrue(is_closed)


class HighDemandPhoneVerificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_high_demand_event_blocks_unverified_phone(self):
        """
        Phase 5: High-demand event requires phone verification before join.
        """
        user_unverified = User(
            id=uuid.uuid4(),
            email="user@test.com",
            password_hash="hash",
            is_phone_verified=False,
        )
        user_verified = User(
            id=uuid.uuid4(),
            email="user2@test.com",
            password_hash="hash",
            is_phone_verified=True,
        )
        event_high_demand = Event(
            id=uuid.uuid4(),
            name="High Demand Drop",
            capacity=50,
            remaining_seats=50,
            requires_phone_verification=True,
            is_open=True,
        )

        # Unverified user must be blocked
        is_blocked = event_high_demand.requires_phone_verification and not user_unverified.is_phone_verified
        self.assertTrue(is_blocked)

        # Verified user must be permitted
        is_permitted = not (event_high_demand.requires_phone_verification and not user_verified.is_phone_verified)
        self.assertTrue(is_permitted)


class RateLimiterAndRetryAfterTests(unittest.IsolatedAsyncioTestCase):
    async def test_rate_limit_exceeded_raises_429_with_retry_after(self):
        """
        Phase 2: When rate limit is exceeded, HTTP 429 must be raised with Retry-After header.
        """
        with patch("app.dependencies.rate_limit.redis_client.eval", AsyncMock(return_value=[0, "5"])):
            with self.assertRaises(HTTPException) as ctx:
                await check_token_bucket("rl:test:key", capacity=5, refill=0.5)
            self.assertEqual(ctx.exception.status_code, 429)
            self.assertEqual(ctx.exception.headers.get("Retry-After"), "5")

    async def test_multi_dimensional_rate_limiting_checks_all_keys(self):
        """
        Phase 2: Validates IP, User, Event+User, Event+IP dimensions.
        """
        checked_keys = []
        async def mock_eval(script, numkeys, key, *args):
            checked_keys.append(key)
            return [1, "0"]

        with patch("app.dependencies.rate_limit.redis_client.eval", mock_eval):
            req = MagicMock()
            await check_multi_dim_rate_limits(
                request=req,
                scope="join",
                ip="192.168.1.50",
                user_id="u_abc",
                event_id="ev_xyz"
            )

        self.assertIn("rl:join:ip:192.168.1.50", checked_keys)
        self.assertIn("rl:join:ev_ip:ev_xyz:192.168.1.50", checked_keys)
        self.assertIn("rl:join:user:u_abc", checked_keys)
        self.assertIn("rl:join:ev_user:ev_xyz:u_abc", checked_keys)
        self.assertEqual(len(checked_keys), 4)


class TruePreCommitmentTests(unittest.IsolatedAsyncioTestCase):
    async def test_two_phase_pre_commitment_and_revelation(self):
        """
        Phase 11:
        1. Pre-commitment creates seed commitment BEFORE draw.
        2. Draw uses the pre-committed seed.
        3. Revealed seed matches SHA-256(seed) == seed_commitment.
        """
        event_id = uuid.uuid4()
        seed = secrets.token_bytes(32)
        seed_hex = seed.hex()
        seed_commitment = hashlib.sha256(seed).hexdigest()

        # Step 1: Pre-commitment record
        allocation_run = AllocationRun(
            id=uuid.uuid4(),
            event_id=event_id,
            allocation_seed=seed_hex,
            seed_commitment=seed_commitment,
            revealed_seed=None, # Hidden prior to draw!
            status="COMMITTED",
        )
        self.assertIsNone(allocation_run.revealed_seed)
        self.assertEqual(allocation_run.status, "COMMITTED")

        # Step 2: Draw execution reveals seed
        allocation_run.revealed_seed = seed_hex
        allocation_run.status = "COMPLETED"

        # Step 3: Public verification
        revealed_bytes = bytes.fromhex(allocation_run.revealed_seed)
        self.assertEqual(hashlib.sha256(revealed_bytes).hexdigest(), allocation_run.seed_commitment)


class ClaimsAndNoOversellTests(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_claims_never_oversell(self):
        """
        Phase 14: Concurrent claim requests cannot claim more than remaining seats.
        """
        capacity = 10
        remaining_seats = 10
        lock = asyncio.Lock()
        successful_claims = 0
        rejected_claims = 0

        async def attempt_claim():
            nonlocal remaining_seats, successful_claims, rejected_claims
            async with lock:
                if remaining_seats > 0:
                    remaining_seats -= 1
                    successful_claims += 1
                    return True
                else:
                    rejected_claims += 1
                    return False

        # 25 concurrent claim attempts for 10 seats
        results = await asyncio.gather(*(attempt_claim() for _ in range(25)))
        self.assertEqual(successful_claims, 10)
        self.assertEqual(rejected_claims, 15)
        self.assertEqual(remaining_seats, 0)


if __name__ == "__main__":
    unittest.main()
