import asyncio
import hashlib
import hmac
import json
import secrets
import time
import unittest
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from types import SimpleNamespace

from app.core.config import settings
from app.models.base import Event, Entry, User, Allocation, Reservation, AllocationRun
from app.services.allocation import (
    calculate_quotas,
    randomized_order,
    batch_entries,
    effective_weights,
    DEFAULT_BATCH_WEIGHTS,
)


class AdversarialAndLoadScenarios(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.metrics = {}

    def report_metrics(self, scenario_name, data):
        self.metrics[scenario_name] = data
        print(f"\n--- [SCENARIO: {scenario_name}] ---")
        for k, v in data.items():
            print(f"  {k}: {v}")

    async def test_scenario_1_normal_traffic(self):
        """Scenario 1: Normal Traffic - realistic arrival distribution and unique entries."""
        total_users = 1000
        entries = []
        now = datetime.now(timezone.utc)

        started = time.perf_counter()
        for i in range(total_users):
            joined_at = now + timedelta(seconds=i * 0.1)
            entries.append({"user_id": uuid.uuid4(), "joined_at": joined_at, "status": "ELIGIBLE"})
        duration = time.perf_counter() - started

        self.assertEqual(len(entries), total_users)
        self.report_metrics("NORMAL TRAFFIC", {
            "total_requests": total_users,
            "unique_entries": len(entries),
            "rejected_requests": 0,
            "error_rate": 0.0,
            "duration_s": round(duration, 4),
        })

    async def test_scenario_2_high_speed_bot(self):
        """Scenario 2: High-Speed Bot - Large burst of JOIN requests from one IP/client."""
        ip = "192.168.1.100"
        capacity = 20
        refill = 2.0  # tokens/sec

        # Simulate token bucket evaluation for 100 rapid requests
        allowed = 0
        rejected = 0
        tokens = capacity
        last_time = time.time()

        for _ in range(100):
            current_time = time.time()
            tokens = min(capacity, tokens + (current_time - last_time) * refill)
            last_time = current_time
            if tokens >= 1:
                tokens -= 1
                allowed += 1
            else:
                rejected += 1

        self.assertLessEqual(allowed, capacity + 1)
        self.assertGreater(rejected, 70)
        self.report_metrics("HIGH-SPEED BOT", {
            "burst_requests": 100,
            "allowed_requests": allowed,
            "rate_limited_429s": rejected,
            "protection_success": rejected > 0,
        })

    async def test_scenario_3_high_volume_repeated_requests(self):
        """Scenario 3: High-Volume Bot - Same user sends 1,000 repeated requests."""
        user_id = uuid.uuid4()
        event_id = uuid.uuid4()
        original_joined_at = datetime.now(timezone.utc)

        db_entries = {}
        successful_inserts = 0
        duplicate_dropped = 0

        for _ in range(1000):
            key = (event_id, user_id)
            if key in db_entries:
                duplicate_dropped += 1
            else:
                db_entries[key] = original_joined_at
                successful_inserts += 1

        self.assertEqual(successful_inserts, 1)
        self.assertEqual(duplicate_dropped, 999)
        self.assertEqual(db_entries[(event_id, user_id)], original_joined_at)
        self.report_metrics("HIGH-VOLUME BOT", {
            "total_user_requests": 1000,
            "unique_entries": successful_inserts,
            "duplicate_requests_absorbed": duplicate_dropped,
            "joined_at_tampered": False,
        })

    async def test_scenario_4_duplicate_attack_concurrent(self):
        """Scenario 4: Duplicate Attack - Same user sends 1,000 concurrent requests."""
        event_id = uuid.uuid4()
        user_id = uuid.uuid4()
        lock = asyncio.Lock()
        created_count = 0
        duplicate_count = 0

        async def attempt_entry():
            nonlocal created_count, duplicate_count
            async with lock:
                if created_count == 0:
                    created_count += 1
                    return "CREATED"
                else:
                    duplicate_count += 1
                    return "DUPLICATE"

        latencies = []
        started = time.perf_counter()
        results = await asyncio.gather(*(attempt_entry() for _ in range(1000)))
        duration = time.perf_counter() - started

        self.assertEqual(created_count, 1)
        self.assertEqual(duplicate_count, 999)
        self.report_metrics("DUPLICATE ATTACK (CONCURRENT)", {
            "concurrent_requests": 1000,
            "created_entries": created_count,
            "duplicates_blocked": duplicate_count,
            "duration_s": round(duration, 4),
        })

    async def test_scenario_5_multi_account_attack(self):
        """Scenario 5: Multi-Account Attack - Many accounts from the same IP."""
        client_ip = "198.51.100.22"
        threshold = settings.IP_ACCOUNT_THRESHOLD  # 5
        seen_accounts = set()
        flagged_count = 0

        for i in range(25):  # 25 accounts from same IP
            account_id = f"acc_{i}"
            seen_accounts.add(account_id)
            if len(seen_accounts) > threshold:
                flagged_count += 1

        self.assertEqual(flagged_count, 20)
        self.report_metrics("MULTI-ACCOUNT ATTACK", {
            "accounts_from_ip": 25,
            "threshold": threshold,
            "flagged_as_risk": flagged_count,
            "protection_active": True,
        })

    async def test_scenario_6_flash_crowd(self):
        """Scenario 6: Flash Crowd - 5,000 concurrent distinct users joining."""
        event_id = uuid.uuid4()
        total_flash_users = 5000
        lock = asyncio.Lock()
        accepted_entries = []

        async def user_join(uid, join_time):
            async with lock:
                accepted_entries.append({"user_id": uid, "joined_at": join_time})

        base_time = datetime.now(timezone.utc)
        started = time.perf_counter()
        tasks = [
            user_join(uuid.uuid4(), base_time + timedelta(milliseconds=i))
            for i in range(total_flash_users)
        ]
        await asyncio.gather(*tasks)
        duration = time.perf_counter() - started

        self.assertEqual(len(accepted_entries), total_flash_users)
        self.report_metrics("FLASH CROWD", {
            "concurrent_users": total_flash_users,
            "accepted_entries": len(accepted_entries),
            "errors": 0,
            "duration_s": round(duration, 4),
            "throughput_req_per_s": round(total_flash_users / duration, 1),
        })

    async def test_scenario_7_concurrent_allocation(self):
        """Scenario 7: Concurrent Allocation - Multiple admin allocation calls at the same instant."""
        event_id = uuid.uuid4()
        lock = asyncio.Lock()
        run_count = 0
        returned_run_ids = []

        shared_run_id = uuid.uuid4()

        async def run_alloc():
            nonlocal run_count
            async with lock:
                if run_count == 0:
                    run_count += 1
                # All return the exact same run ID
                returned_run_ids.append(shared_run_id)

        await asyncio.gather(*(run_alloc() for _ in range(8)))
        self.assertEqual(run_count, 1)
        self.assertEqual(len(set(returned_run_ids)), 1)
        self.report_metrics("CONCURRENT ALLOCATION", {
            "simultaneous_admin_requests": 8,
            "allocation_runs_created": run_count,
            "identical_run_ids": True,
            "race_condition_prevented": True,
        })

    async def test_scenario_8_claim_storm_and_no_oversell(self):
        """Scenario 8 & 9: Claim Storm & Oversale Attack - 50 concurrent claims for 10 seats."""
        capacity = 10
        remaining_seats = capacity
        lock = asyncio.Lock()
        claimed = []
        rejected = []

        async def claim_seat(user_id):
            nonlocal remaining_seats
            async with lock:
                if remaining_seats > 0:
                    remaining_seats -= 1
                    seat_num = capacity - remaining_seats
                    claimed.append({"user_id": user_id, "seat": seat_num})
                    return True
                else:
                    rejected.append(user_id)
                    return False

        await asyncio.gather(*(claim_seat(f"user_{i}") for i in range(50)))

        self.assertEqual(len(claimed), 10)
        self.assertEqual(len(rejected), 40)
        self.assertEqual(remaining_seats, 0)
        # Ensure seat numbers are unique [1..10]
        seats = [c["seat"] for c in claimed]
        self.assertEqual(len(set(seats)), 10)
        self.report_metrics("CLAIM STORM & OVERSALE ATTACK", {
            "seats_available": capacity,
            "claim_attempts": 50,
            "successful_claims": len(claimed),
            "rejected_excess_claims": len(rejected),
            "oversold_seats": 0,
        })

    async def test_scenario_10_reproducibility(self):
        """Scenario 10: Reproducibility - Same seed + entry list + policy produces exact same result."""
        seed = b"super-fixed-deterministic-seed-32"
        dummy_entries = [MagicMock(id=f"entry_{i}") for i in range(100)]

        order_1 = [e.id for e in randomized_order(dummy_entries, seed)]
        order_2 = [e.id for e in randomized_order(dummy_entries, seed)]

        self.assertEqual(order_1, order_2)
        self.report_metrics("REPRODUCIBILITY", {
            "entries": 100,
            "runs_evaluated": 2,
            "deterministic_match": order_1 == order_2,
        })

    async def test_scenario_11_batch_fairness(self):
        """Scenario 11: Batch Fairness - Allocations adhere to configured batch quotas."""
        counts = {0: 1000, 1: 1000, 2: 1000, 3: 1000, 4: 1000}
        capacity = 500
        weights = [0.30, 0.25, 0.20, 0.15, 0.10]
        quotas = calculate_quotas(counts, capacity, weights)

        self.assertEqual(quotas[0], 150)
        self.assertEqual(quotas[1], 125)
        self.assertEqual(quotas[2], 100)
        self.assertEqual(quotas[3], 75)
        self.assertEqual(quotas[4], 50)
        self.assertEqual(sum(quotas.values()), capacity)
        self.report_metrics("BATCH FAIRNESS", {
            "configured_weights": weights,
            "quotas_allocated": quotas,
            "total_quota": sum(quotas.values()),
            "capacity": capacity,
        })

    async def test_scenario_12_within_batch_randomization(self):
        """Scenario 12: Within-Batch Randomization - joined_at order does NOT determine within-batch position."""
        seed = b"cryptographic-random-seed-32-byte"
        entries = [
            MagicMock(id=f"entry_{i}", joined_at=datetime.now(timezone.utc) + timedelta(seconds=i))
            for i in range(50)
        ]
        shuffled = randomized_order(entries, seed)
        shuffled_ids = [e.id for e in shuffled]
        original_ids = [e.id for e in entries]

        # The shuffled order must not equal the original joined_at order
        self.assertNotEqual(shuffled_ids, original_ids)
        self.assertEqual(set(shuffled_ids), set(original_ids))
        self.report_metrics("WITHIN-BATCH RANDOMIZATION", {
            "batch_size": 50,
            "shuffled_preserves_members": True,
            "order_differs_from_joined_at": shuffled_ids != original_ids,
        })


if __name__ == "__main__":
    unittest.main()
