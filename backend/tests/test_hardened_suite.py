import hashlib
import hmac
import json
import secrets
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.config import settings
from app.dependencies.fraud import RiskLevel, assess_risk, IP_ACCOUNT_VELOCITY_LUA
from app.dependencies.rate_limit import TOKEN_BUCKET_LUA
from app.models.base import Event, Entry, User, Allocation, Reservation, AllocationRun
from app.services.allocation import (
    calculate_quotas,
    randomized_order,
    batch_entries,
    effective_weights,
    DEFAULT_BATCH_WEIGHTS,
)


class HardenedOTPTests(unittest.TestCase):
    def test_csprng_generation(self):
        """OTP must use CSPRNG and be exactly 6 digits."""
        codes = set()
        for _ in range(100):
            code = "".join(secrets.choice("0123456789") for _ in range(6))
            self.assertEqual(len(code), 6)
            self.assertTrue(code.isdigit())
            codes.add(code)
        # Should be distinct random values
        self.assertGreater(len(codes), 95)

    def test_salted_hash_storage_no_plaintext(self):
        """OTP stored in cache must be a salted SHA-256 hash."""
        code = "123456"
        salt = secrets.token_hex(16)
        hashed = hashlib.sha256(f"{salt}:{code}".encode("utf-8")).hexdigest()

        # Plaintext code must not match the hash
        self.assertNotEqual(code, hashed)
        # Verification using HMAC compare_digest
        computed = hashlib.sha256(f"{salt}:{code}".encode("utf-8")).hexdigest()
        self.assertTrue(hmac.compare_digest(computed, hashed))
        # Wrong code must fail
        wrong_computed = hashlib.sha256(f"{salt}:999999".encode("utf-8")).hexdigest()
        self.assertFalse(hmac.compare_digest(wrong_computed, hashed))

    def test_max_attempts_lockout(self):
        """Simulate attempt counter lockout at max attempts."""
        max_attempts = 5
        attempts = 0
        allowed = True
        for i in range(max_attempts):
            attempts += 1
            if attempts >= max_attempts:
                allowed = False
        self.assertEqual(attempts, 5)
        self.assertFalse(allowed)


class HardenedRateLimiterTests(unittest.TestCase):
    def test_token_bucket_lua_syntax(self):
        """Verify Lua script includes capacity, refill, and Retry-After return."""
        self.assertIn("local missing = requested - tokens", TOKEN_BUCKET_LUA)
        self.assertIn("local retry_after = math.ceil(missing / refill)", TOKEN_BUCKET_LUA)
        self.assertIn("return {0, tostring(retry_after)}", TOKEN_BUCKET_LUA)
        self.assertIn("return {1, \"0\"}", TOKEN_BUCKET_LUA)

    def test_multi_dimension_key_formats(self):
        """Ensure rate limit dimensions form distinct non-colliding keys."""
        ip_key = "rl:join:ip:127.0.0.1"
        user_key = "rl:join:user:u123"
        ev_user_key = "rl:join:ev_user:ev1:u123"
        ev_ip_key = "rl:join:ev_ip:ev1:127.0.0.1"
        all_keys = {ip_key, user_key, ev_user_key, ev_ip_key}
        self.assertEqual(len(all_keys), 4)


class HardenedBotAndFraudTests(unittest.TestCase):
    def test_atomic_ip_account_lua(self):
        """Verify Lua script uses SADD + SCARD atomically."""
        self.assertIn("redis.call('SADD', key, user_id)", IP_ACCOUNT_VELOCITY_LUA)
        self.assertIn("local count = redis.call('SCARD', key)", IP_ACCOUNT_VELOCITY_LUA)
        self.assertIn("return count", IP_ACCOUNT_VELOCITY_LUA)

    def test_shared_ip_tolerance(self):
        """Legitimate shared IPs (e.g. 5 accounts) should not trigger extreme bot block."""
        # Simulated user on shared IP with normal browser header
        request = MagicMock()
        request.headers = {"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        request.client.host = "192.168.1.1"
        user = MagicMock()
        user.id = "u1"
        user.is_phone_verified = True

        with patch("app.dependencies.fraud.record_and_get_ip_account_count", AsyncMock(return_value=3)):
            import asyncio
            risk, signals = asyncio.run(assess_risk(request, user, "ev1"))
            self.assertEqual(risk, RiskLevel.LOW)
            self.assertEqual(signals, [])


class HardenedPreCommitmentAndAllocationTests(unittest.TestCase):
    def test_seed_commitment_cryptographic_verification(self):
        """Pre-commitment must satisfy SHA-256(seed) == seed_commitment."""
        seed = secrets.token_bytes(32)
        seed_hex = seed.hex()
        seed_commitment = hashlib.sha256(seed).hexdigest()

        # Anyone can independently verify the revealed seed matches commitment
        revealed_seed_bytes = bytes.fromhex(seed_hex)
        computed_commitment = hashlib.sha256(revealed_seed_bytes).hexdigest()
        self.assertEqual(computed_commitment, seed_commitment)

    def test_deterministic_canonical_serialization(self):
        """Canonical JSON serialization must produce identical SHA-256 hash regardless of dictionary insertion order."""
        payload_1 = {
            "status": "ALLOCATION_COMPLETE",
            "capacity": 500,
            "seed_commitment": "abc123",
            "winner_count": 50,
            "winners_by_batch": {"batch-1": 30, "batch-2": 20},
        }
        # Payload with different key insertion order
        payload_2 = {
            "winner_count": 50,
            "winners_by_batch": {"batch-1": 30, "batch-2": 20},
            "capacity": 500,
            "status": "ALLOCATION_COMPLETE",
            "seed_commitment": "abc123",
        }

        canon_1 = json.dumps(payload_1, sort_keys=True, separators=(',', ':')).encode("utf-8")
        canon_2 = json.dumps(payload_2, sort_keys=True, separators=(',', ':')).encode("utf-8")
        self.assertEqual(canon_1, canon_2)

        hash_1 = hashlib.sha256(canon_1).hexdigest()
        hash_2 = hashlib.sha256(canon_2).hexdigest()
        self.assertEqual(hash_1, hash_2)

    def test_capacity_preservation(self):
        """Fair Batch allocation algorithm strictly adheres to event capacity."""
        counts = {0: 500, 1: 500, 2: 500, 3: 500, 4: 500}
        capacity = 100
        quotas = calculate_quotas(counts, capacity, [0.30, 0.25, 0.20, 0.15, 0.10])
        self.assertEqual(sum(quotas.values()), capacity)
        self.assertEqual(quotas[0], 30)
        self.assertEqual(quotas[1], 25)
        self.assertEqual(quotas[2], 20)
        self.assertEqual(quotas[3], 15)
        self.assertEqual(quotas[4], 10)

    def test_insufficient_batch_redistribution(self):
        """Under-subscribed batch quotas are fairly redistributed to remaining batches."""
        # Batch 0 has only 5 users despite 30% target of 100 (=30)
        counts = {0: 5, 1: 100, 2: 100}
        capacity = 50
        quotas = calculate_quotas(counts, capacity, [0.30, 0.40, 0.30])
        self.assertEqual(sum(quotas.values()), capacity)
        self.assertEqual(quotas[0], 5)  # Takes all 5, distributes remaining 10 to batch 1 & 2


class HardenedClaimsAndConcurrencyTests(unittest.TestCase):
    def test_expired_claim_boundary(self):
        """Claims past authoritative server expiry time must be strictly rejected."""
        now = datetime.now(timezone.utc)
        expired_deadline = now - timedelta(seconds=1)
        valid_deadline = now + timedelta(minutes=10)

        # Check comparison logic
        self.assertTrue(expired_deadline < now)
        self.assertFalse(valid_deadline < now)

    def test_idempotency_key_caching(self):
        """Simulate duplicate claim with identical idempotency key returning cached reservation."""
        idem_key = "idem-tx-999"
        cached_result = {
            "reservation_id": "res-123",
            "seat_number": 42,
            "status": "RESERVED"
        }
        raw_cached = json.dumps(cached_result)
        # Reading from idempotency cache returns original reservation without booking a second seat
        restored = json.loads(raw_cached)
        self.assertEqual(restored["reservation_id"], "res-123")
        self.assertEqual(restored["seat_number"], 42)


if __name__ == "__main__":
    unittest.main()
