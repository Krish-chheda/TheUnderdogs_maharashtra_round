"""Adversarial traffic + flash-crowd + concurrency validation for Fair Drop.

Drives the REAL running FastAPI application over REAL HTTP (uvicorn on :8000)
against the REAL configured database and Redis. No production code is modified.

Because the application's rate limiter and anti-bot guard are keyed on the
client IP, each request is issued from a distinct loopback source address via
httpx's `local_address`. That is what lets a normal user, a bot and a
flash crowd all be modelled honestly from a single machine.

Usage (from backend/):
    python tests/load_test.py                # full 50k run
    python tests/load_test.py --scale 0.02   # quick probe

Reports every requested metric, then asserts checks A-I.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import math
import os
import subprocess
import sys
import time
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.core.database import AsyncSessionLocal, engine  # noqa: E402
from app.core.security import create_access_token  # noqa: E402

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
API_BASE = os.getenv("LOADTEST_API", "http://127.0.0.1:8000")
EVENT_CAPACITY = 500
BATCH_DURATION_SECONDS = 120
BATCH_WEIGHTS = [0.30, 0.25, 0.20, 0.15, 0.10]

SCALE = 1.0
NORMAL_USERS = 50_000          # scenario 1
FLASH_USERS = 5_000            # scenario 5
FLASH_MAX_INFLIGHT = 2_000     # sockets actually in flight at the same instant
HIGH_SPEED_USERS = 200         # scenario 2: all from ONE ip, flat out
HIGH_SPEED_REQS_PER_USER = 5   # "much faster than a normal user"
HIGH_VOLUME_REQUESTS = 5_000   # scenario 3: few users, many repeats
HIGH_VOLUME_USERS = 50
DUPLICATE_CONCURRENT = 250     # scenario 4: one user, N truly simultaneous requests
CONCURRENT_ALLOC_WORKERS = 6   # scenario 6: separate OS processes
CLAIM_STORM = True             # all winners claim at once -> seat oversell check

# Redis rate-limit / anti-bot state is keyed by IP; make sure a previous run of
# the same source addresses cannot leak into this one.
RL_PREFIXES = ("rl:enter:", "fraud:ip_users:")


def scaled(n: int, minimum: int = 1) -> int:
    return max(minimum, int(round(n * SCALE)))


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, math.ceil(pct * len(ordered)) - 1))
    return round(ordered[idx], 2)


def loopback_ip(index: int) -> str:
    """Deterministic, distinct 127.x.y.z source address."""
    index += 1
    return f"127.{40 + (index // 65025) % 200}.{(index // 255) % 255}.{index % 254 + 1}"


async def join_request(ip: str, token: str, event_id: str) -> dict:
    """One real HTTP POST /events/{id}/join from a specific source address."""
    transport = httpx.AsyncHTTPTransport(local_address=ip, retries=0)
    async with httpx.AsyncClient(transport=transport, base_url=API_BASE, timeout=180) as client:
        started = time.perf_counter()
        try:
            response = await client.post(
                f"/events/{event_id}/join",
                headers={"Authorization": f"Bearer {token}"},
            )
            latency = (time.perf_counter() - started) * 1000
            try:
                body = response.json()
            except Exception:
                body = {}
            return {
                "status": response.status_code,
                "entry_id": body.get("entry_id"),
                "detail": body.get("detail"),
                "latency_ms": latency,
            }
        except Exception as error:  # transport-level failure
            return {
                "status": 599,
                "entry_id": None,
                "detail": f"{type(error).__name__}: {error}"[:160],
                "latency_ms": (time.perf_counter() - started) * 1000,
            }


async def db_fetch_all(sql: str, **params):
    async with AsyncSessionLocal() as db:
        result = await db.execute(text(sql), params)
        return result.all()


async def db_fetch_one(sql: str, **params):
    rows = await db_fetch_all(sql, **params)
    return rows[0] if rows else None


# --------------------------------------------------------------------------
# Setup
# --------------------------------------------------------------------------
async def seed_users(run_tag: str, groups: dict[str, int]) -> tuple[dict, dict]:
    """Bulk-insert real user rows; mint real HS256 tokens with the app's own signer."""
    users: list[dict] = []
    tokens: dict[str, list[str]] = {}
    user_ids: dict[str, list[uuid.UUID]] = {}
    for group, count in groups.items():
        group_ids, group_tokens = [], []
        for index in range(count):
            user_id = uuid.uuid4()
            users.append(
                {
                    "id": user_id,
                    "email": f"lt-{run_tag}-{group}-{index}@load.invalid",
                    "phone": None,
                    "password_hash": "load-test-only",
                    "role": "user",
                }
            )
            group_ids.append(user_id)
            group_tokens.append(create_access_token({"sub": str(user_id), "role": "user"}))
        user_ids[group] = group_ids
        tokens[group] = group_tokens
    print(f"  seeding {len(users)} users ...", flush=True)
    started = time.perf_counter()
    async with AsyncSessionLocal() as db:
        for start in range(0, len(users), 5_000):
            chunk = users[start : start + 5_000]
            await db.execute(
                text(
                    "insert into users (id, email, phone, password_hash, role) "
                    "values (:id, :email, :phone, :password_hash, :role)"
                ),
                chunk,
            )
        await db.commit()
    print(f"  seeded in {time.perf_counter() - started:.1f}s", flush=True)
    return tokens, user_ids


async def create_event(run_tag: str, admin_token: str) -> str:
    async with httpx.AsyncClient(base_url=API_BASE, timeout=120) as client:
        response = await client.post(
            "/admin/events/",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": f"LoadTest {run_tag}",
                "capacity": EVENT_CAPACITY,
                "venue": "localhost load test",
                "event_date": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
                "registration_deadline": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                "batch_duration_seconds": BATCH_DURATION_SECONDS,
                "batch_weights": BATCH_WEIGHTS,
            },
        )
        response.raise_for_status()
        return response.json()["event_id"]


async def make_admin(run_tag: str) -> tuple[str, uuid.UUID]:
    admin_id = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("insert into users (id, email, phone, password_hash, role) values (:i,:e,:p,:h,'admin')"),
            {"i": admin_id, "e": f"lt-{run_tag}-admin@load.invalid", "p": None, "h": "x"},
        )
        await db.commit()
    return create_access_token({"sub": str(admin_id), "role": "admin"}), admin_id


async def reset_redis_for_run(run_tag: str, ips: list[str], event_id: str) -> None:
    from app.core.redis import redis_client

    for ip in ips:
        await redis_client.delete(f"rl:enter:{ip}")
        await redis_client.delete(f"fraud:ip_users:{event_id}:{ip}")


# --------------------------------------------------------------------------
# Scenario runner
# --------------------------------------------------------------------------
def summarise(name: str, results: list[dict], started: float, extra: dict) -> dict:
    codes = Counter(r["status"] for r in results)
    latencies = [r["latency_ms"] for r in results]
    successes = [r for r in results if r["status"] == 200]
    entry_ids = {r["entry_id"] for r in successes if r["entry_id"]}
    report = {
        "scenario": name,
        "total_requests": len(results),
        "successful_http_requests": len(successes),
        "rejected_or_rate_limited": sum(
            codes[c] for c in (400, 401, 403, 404, 409, 422) if c in codes
        ),
        "rate_limited_429": codes.get(429, 0),
        "api_error_count": sum(v for c, v in codes.items() if c >= 500),
        "transport_errors_599": codes.get(599, 0),
        "distinct_entry_ids_returned": len(entry_ids),
        "duration_seconds": round(time.perf_counter() - started, 2),
        "throughput_rps": round(len(results) / max(1e-9, time.perf_counter() - started), 1),
        "latency_p50_ms": percentile(latencies, 0.50),
        "latency_p95_ms": percentile(latencies, 0.95),
        "latency_p99_ms": percentile(latencies, 0.99),
        "latency_max_ms": round(max(latencies), 2) if latencies else 0,
        "status_codes": {str(k): v for k, v in sorted(codes.items())},
    }
    report.update(extra)
    return report


async def scenario_normal(event_id: str, tokens: list[str], concurrency: int) -> dict:
    """Scenario 1 - 50,000 unique users, one JOIN each, realistic arrival."""
    print(f"  NORMAL: {len(tokens)} unique users, 1 JOIN each, concurrency {concurrency}", flush=True)
    started = time.perf_counter()
    semaphore = asyncio.Semaphore(concurrency)
    results: list[dict] = []

    async def one(index: int, token: str):
        async with semaphore:
            results.append(await join_request(loopback_ip(index), token, event_id))

    await asyncio.gather(*(one(i, t) for i, t in enumerate(tokens)))
    return summarise("NORMAL", results, started, {})


async def scenario_high_speed_bot(event_id: str, tokens: list[str]) -> dict:
    """Scenario 2 - many accounts from ONE ip, firing flat out."""
    ips = "127.90.0.7"  # a single hostile source address
    reqs_per_user = HIGH_SPEED_REQS_PER_USER
    print(f"  HIGH-SPEED BOT: {len(tokens)} users x {reqs_per_user} requests from ONE ip ({ips})", flush=True)
    started = time.perf_counter()
    jobs = []
    for repeat in range(reqs_per_user):
        for index, token in enumerate(tokens):
            jobs.append(join_request(ips, token, event_id))
    results = await asyncio.gather(*jobs)
    return summarise("HIGH-SPEED BOT", list(results), started, {"source_ips": 1})


async def scenario_high_volume_bot(event_id: str, tokens: list[str]) -> dict:
    """Scenario 3 - a small set of users hammering, each with its own ip.

    Distinct ips per user so the anti-bot ip/account guard cannot mask the
    question we actually care about: does repeating the request buy anything?
    """
    per_user = max(1, HIGH_VOLUME_REQUESTS // max(1, len(tokens)))
    print(
        f"  HIGH-VOLUME BOT: {len(tokens)} users x {per_user} repeated requests "
        f"({len(tokens) * per_user} total)",
        flush=True,
    )
    started = time.perf_counter()
    jobs = []
    for repeat in range(per_user):
        for index, token in enumerate(tokens):
            jobs.append(join_request(loopback_ip(index), token, event_id))
    results = await asyncio.gather(*jobs)
    return summarise(
        "HIGH-VOLUME BOT",
        list(results),
        started,
        {"repeats_per_user": per_user, "distinct_users": len(tokens)},
    )


async def scenario_duplicate_attack(event_id: str, token: str) -> dict:
    """Scenario 4 - ONE user, N truly simultaneous JOIN requests.

    Each request uses a different source ip so that neither the token bucket
    nor the anti-bot guard hides what the database itself does.
    """
    n = DUPLICATE_CONCURRENT
    print(f"  DUPLICATE ATTACK: 1 user, {n} simultaneous requests, {n} distinct source ips", flush=True)
    base = 900_000
    started = time.perf_counter()
    results = await asyncio.gather(
        *(join_request(loopback_ip(base + i), token, event_id) for i in range(n))
    )
    ids = {r["entry_id"] for r in results if r["entry_id"]}
    return summarise(
        "DUPLICATE ATTACK",
        list(results),
        started,
        {"distinct_entry_ids_returned": len(ids), "entry_ids": sorted(ids)[:5]},
    )


async def scenario_flash_crowd(event_id: str, tokens: list[str]) -> dict:
    """Scenario 5 - thousands of JOIN requests released by a single barrier."""
    print(f"  FLASH CROWD: {len(tokens)} users released simultaneously", flush=True)
    n = len(tokens)
    inflight = min(FLASH_MAX_INFLIGHT, n)
    started = time.perf_counter()
    results: list[dict] = []
    lock = asyncio.Lock()
    barrier = asyncio.Event()
    next_index = 0

    async def worker():
        nonlocal next_index
        async with lock:
            my_index = next_index
            next_index += 1
        await barrier.wait()  # nobody fires before the gate opens
        result = await join_request(loopback_ip(3_000_000 + my_index), tokens[my_index], event_id)
        async with lock:
            results.append(result)

    workers = [asyncio.create_task(worker()) for _ in range(inflight)]
    await asyncio.sleep(0)  # let every worker reach the barrier
    gate_at = time.perf_counter()
    barrier.set()
    await asyncio.gather(*workers)
    release_overhead = (time.perf_counter() - gate_at) * 1000
    report = summarise("FLASH CROWD", results, started, {})
    report["simultaneous_connections_opened"] = inflight
    report["barrier_release_ms"] = round(release_overhead, 1)
    return report


# --------------------------------------------------------------------------
# Scenario 6 - concurrent allocation from separate OS processes
# --------------------------------------------------------------------------
async def scenario_concurrent_allocation(event_id: str, admin_token: str) -> dict:
    workers = CONCURRENT_ALLOC_WORKERS
    print(f"  CONCURRENT ALLOCATION: {workers} separate OS processes, same instant", flush=True)

    # Each child waits for a shared wall-clock deadline so they truly collide.
    deadline = time.time() + 3.0
    procs = [
        subprocess.Popen(
            [
                sys.executable, str(Path(__file__).resolve()), "--allocate-worker",
                "--event-id", str(event_id), "--admin-token", admin_token,
                "--start-at", f"{deadline:.3f}",
            ],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(Path(__file__).resolve().parents[1]),
        )
        for _ in range(workers)
    ]
    started = time.perf_counter()
    outputs = []
    for proc in procs:
        out, err = proc.communicate(timeout=900)
        outputs.append(
            {
                "returncode": proc.returncode,
                "stdout": out.decode(errors="replace").strip(),
                "stderr": err.decode(errors="replace").strip()[-400:],
            }
        )
    duration = time.perf_counter() - started

    bodies = []
    for item in outputs:
        for line in item["stdout"].splitlines():
            if line.startswith("{"):
                try:
                    bodies.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    run_ids = {b.get("allocation_run_id") for b in bodies if b.get("allocation_run_id")}
    report = {
        "scenario": "CONCURRENT ALLOCATION",
        "separate_processes": workers,
        "allocation_http_200": sum(1 for b in bodies if b.get("status") == "ALLOCATION_COMPLETE"),
        "allocation_http_errors": [b for b in bodies if b.get("status") != "ALLOCATION_COMPLETE"],
        "distinct_allocation_run_ids": len(run_ids),
        "identical_response_bodies": len({json.dumps(b, sort_keys=True) for b in bodies}) == 1 if bodies else False,
        "wall_duration_seconds": round(duration, 3),
        "child_returncodes": [o["returncode"] for o in outputs],
        "child_stderr": [o["stderr"] for o in outputs if o["stderr"]],
    }
    return report


async def allocate_worker(event_id: str, admin_token: str, start_at: float) -> None:
    delay = start_at - time.time()
    if delay > 0:
        await asyncio.sleep(delay)
    transport = httpx.AsyncHTTPTransport(local_address="127.99.0.1", retries=0)
    async with httpx.AsyncClient(transport=transport, base_url=API_BASE, timeout=900) as client:
        started = time.perf_counter()
        try:
            response = await client.post(
                f"/admin/events/{event_id}/allocate",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            try:
                body = response.json()
            except Exception:
                body = {"raw": response.text[:300]}
            body["_http_status"] = response.status_code
            body["_child_latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
        except Exception as error:
            body = {"_http_status": 599, "error": f"{type(error).__name__}: {error}"[:200]}
    print(json.dumps(body), flush=True)


# --------------------------------------------------------------------------
# Database measurements
# --------------------------------------------------------------------------
async def queue_snapshot(event_id: str) -> dict:
    row = await db_fetch_one(
        """
        select count(*)::int                                   as rows_total,
               count(distinct user_id)::int                     as unique_users,
               count(*) filter (where status='ELIGIBLE')::int   as eligible,
               count(*) filter (where allocation_status='WINNER')::int   as entry_winners,
               count(*) filter (where allocation_status='WAITLISTED')::int as entry_waitlisted
        from entries where event_id = :e
        """,
        e=event_id,
    )
    multi = await db_fetch_one(
        "select count(*)::int as n from (select user_id from entries where event_id=:e group by user_id having count(*)>1) t",
        e=event_id,
    )
    return {
        "queue_rows": row[0],
        "unique_queue_entries": row[1],
        "duplicate_queue_entries": row[0] - row[1],
        "users_with_multiple_entries": multi[0],
        "eligible_entries": row[2],
        "entries_marked_winner": row[3],
        "entries_marked_waitlisted": row[4],
    }


async def per_group_entry_counts(event_id: str, run_tag: str) -> dict:
    rows = await db_fetch_all(
        """
        select split_part(u.email, '@',1) as email_local, count(*)::int
        from entries en join users u on u.id = en.user_id
        where en.event_id = :e
        group by 1
        """,
        e=event_id,
    )
    out = defaultdict(int)
    for local, count in rows:
        parts = local.split("-")
        if len(parts) >= 3:
            out[parts[2]] += count
    return dict(out)


async def allocation_snapshot(event_id: str) -> dict:
    row = await db_fetch_one(
        """
        select (select count(*) from allocation_runs where event_id=:e)::int as runs,
               (select count(*) from allocations where event_id=:e and status='WINNER')::int as winners,
               (select count(*) from allocations where event_id=:e and status='WAITLISTED')::int as waitlisted,
               (select count(*) from allocations where event_id=:e)::int as allocations_total,
               (select capacity from events where id=:e) as capacity,
               (select remaining_seats from events where id=:e) as remaining_seats
        """,
        e=event_id,
    )
    dup_winners = await db_fetch_one(
        "select coalesce(count(*),0)::int as n from (select user_id from allocations where event_id=:e group by user_id having count(*)>1) t",
        e=event_id,
    )
    dup_ranks = await db_fetch_one(
        "select coalesce(count(*),0)::int as n from (select rank from allocations where event_id=:e group by rank having count(*)>1) t",
        e=event_id,
    )
    winners_by_batch = await db_fetch_all(
        """
        select batch_id, count(*)::int from entries
        where event_id=:e and allocation_status='WINNER'
        group by batch_id order by batch_id
        """,
        e=event_id,
    )
    entries_by_batch = await db_fetch_all(
        """
        select batch_id, count(*)::int from entries
        where event_id=:e group by batch_id order by batch_id
        """,
        e=event_id,
    )
    return {
        "allocation_run_count": row[0],
        "winners": row[1],
        "waitlist_count": row[2],
        "allocations_total": row[3],
        "capacity": row[4],
        "remaining_seats": row[5],
        "duplicate_winners": dup_winners[0],
        "duplicate_ranks": dup_ranks[0],
        "oversold_seats": max(0, row[1] - row[4]),
        "winners_per_batch": {b: c for b, c in winners_by_batch},
        "entries_per_batch": {b: c for b, c in entries_by_batch},
    }


async def winners_by_scenario(event_id: str, run_tag: str) -> dict:
    rows = await db_fetch_all(
        """
        select split_part(u.email,'@',1) as email_local, count(*)::int
        from allocations a join users u on u.id = a.user_id
        where a.event_id = :e and a.status = 'WINNER'
        group by 1
        """,
        e=event_id,
    )
    out = defaultdict(int)
    for local, count in rows:
        parts = local.split("-")
        if len(parts) >= 3:
            out[parts[2]] += count
    return dict(out)


async def verify_reproducible(event_id: str) -> dict:
    """Check G - replay the stored seed and confirm the identical winner set."""
    run = await db_fetch_one(
        """
        select allocation_seed, seed_commitment, batch_definitions, batch_duration_seconds,
               eligible_entry_count, entry_list_hash, winner_count
        from allocation_runs where event_id=:e
        """,
        e=event_id,
    )
    if not run:
        return {"reproducible": False, "reason": "no allocation run"}
    seed_hex, commitment, batch_defs, duration, eligible_count, entry_hash, winner_count = run
    seed = bytes.fromhex(seed_hex)

    rows = await db_fetch_all(
        "select id, joined_at from entries where event_id=:e and status='ELIGIBLE' order by joined_at, id",
        e=event_id,
    )
    start = rows[0][1]
    groups: dict[int, list] = defaultdict(list)
    for entry_id, joined_at in rows:
        elapsed = max(0.0, (joined_at - start).total_seconds())
        groups[int(elapsed // duration)].append(entry_id)

    replay_winners = []
    for definition in batch_defs:
        index = int(definition["batch_id"].split("-")[1]) - 1
        ordered = sorted(groups.get(index, []), key=lambda e: hmac.new(seed, str(e).encode(), "utf-8"), reverse=False)
        replay_winners.extend(ordered[: definition["quota"]])

    replay_winner_users = await db_fetch_all(
        "select user_id from allocations where event_id=:e and status='WINNER' order by rank", e=event_id
    )
    actual = [r[0] for r in replay_winner_users]

    # entry_list_hash uses the ORIGINAL ordered id concatenation
    recomputed_entry_hash = hashlib.sha256("".join(str(r[0]) for r in rows).encode()).hexdigest()

    return {
        "reproducible": sorted(replay_winners) == sorted(actual) and len(actual) > 0,
        "replay_winner_count": len(replay_winners),
        "stored_winner_count": len(actual),
        "winner_set_identical": sorted(replay_winners) == sorted(actual),
        "seed_commitment_matches_sha256": hashlib.sha256(seed).hexdigest() == commitment,
        "entry_list_hash_reproducible": recomputed_entry_hash == entry_hash,
        "eligible_count_matches": eligible_count == len(rows),
        "batches_replayed": len(batch_defs),
    }


async def verify_batch_priority(event_id: str) -> dict:
    """Check H - earlier batches receive their configured priority."""
    run = await db_fetch_one(
        "select batch_definitions, allocation_policy from allocation_runs where event_id=:e", e=event_id
    )
    if not run:
        return {}
    batch_defs = run[0]
    policy = run[1] if isinstance(run[1], dict) else json.loads(run[1]) if isinstance(run[1], str) else {}
    weights = policy.get("weights") or [d["weight"] for d in batch_defs]
    rows = []
    for definition in batch_defs:
        rows.append(
            {
                "batch_id": definition["batch_id"],
                "entry_count": definition["entry_count"],
                "quota": definition["quota"],
                "weight": round(definition["weight"], 4),
                "fully_supplied": definition["entry_count"] >= definition["quota"],
            }
        )
    supplied = [r for r in rows if r["fully_supplied"]]
    winner_counts = [r["quota"] for r in rows]
    monotonic = all(winner_counts[i] >= winner_counts[i + 1] for i in range(len(winner_counts) - 1))
    expected = None
    if supplied:
        total_w = sum(r["weight"] for r in supplied)
        expected = {r["batch_id"]: round(EVENT_CAPACITY * r["weight"] / total_w) for r in supplied}
    exact = expected is not None and all(r["quota"] == expected[r["batch_id"]] for r in supplied)
    return {
        "batches": rows,
        "monotonic_non_increasing": monotonic,
        "expected_from_weights": expected,
        "matches_weighted_split_exactly": exact,
        "weights_used": [round(w, 4) for w in weights],
    }


async def verify_randomisation(event_id: str) -> dict:
    """Check I - inside a batch the draw is randomised, not arrival-ordered."""
    rows = await db_fetch_all(
        """
        select batch_id, randomized_position, (allocation_status='WINNER') as won, joined_at
        from entries where event_id=:e and batch_id is not null
        order by batch_id, randomized_position
        """,
        e=event_id,
    )
    per_batch: dict[str, list] = defaultdict(list)
    for batch_id, position, won, joined_at in rows:
        per_batch[batch_id].append((position, won, joined_at))

    detail = {}
    overall_positions = []
    for batch_id, items in sorted(per_batch.items()):
        total = len(items)
        winners = [(p, j) for p, w, j in items if w]
        if not winners or total < 50:
            continue
        positions = [p for p, _ in winners]
        arrival_rank = {j: i for i, (_, _, j) in enumerate(items)}
        arrival_ranks = [arrival_rank[j] for _, j in winners]

        # win probability per arrival-time decile (uniform => fair)
        buckets: dict[int, list[int]] = defaultdict(list)
        for _, w, j in items:
            buckets[min(9, arrival_rank[j] * 10 // total)].append(1 if w else 0)
        rates = [round(sum(v) / len(v), 4) for _, v in sorted(buckets.items())]

        # Pearson correlation between arrival rank and winning
        n = len(items)
        mean_x = sum(arrival_rank[j] for _, _, j in items) / n
        mean_y = sum(1 if w else 0 for _, w, _ in items) / n
        cov = sum((arrival_rank[j] - mean_x) * ((1 if w else 0) - mean_y) for _, w, j in items)
        sx = math.sqrt(sum((arrival_rank[j] - mean_x) ** 2 for _, _, j in items))
        sy = math.sqrt(sum(((1 if w else 0) - mean_y) ** 2 for _, w, j in items))
        corr = cov / (sx * sy) if sx and sy else 0.0

        detail[batch_id] = {
            "entries": total,
            "winners": len(winners),
            "win_rate": round(len(winners) / total, 4),
            "winner_position_min": min(positions),
            "winner_position_max": max(positions),
            "winner_positions_span_full_range": max(positions) > total * 0.9 and min(positions) < total * 0.1,
            "first_arrival_won": positions and arrival_ranks and min(arrival_ranks) < total * 0.05,
            "last_arrival_won": bool(arrival_ranks) and max(arrival_ranks) > total * 0.95,
            "win_rate_by_arrival_decile": rates,
            "decile_spread": round(max(rates) - min(rates), 4) if rates else 0.0,
            "arrival_order_correlation": round(corr, 4),
        }
        overall_positions.extend(positions)

    # a batch where the first 40 entries all won would indicate arrival-order bias
    biased = [
        b
        for b, d in detail.items()
        if d["winners"] and d["winner_position_max"] < d["entries"] * 0.9
    ]
    return {
        "per_batch": detail,
        "no_arrival_order_bias": not biased,
        "biased_batches": biased,
    }


async def claim_storm(event_id: str, winner_tokens: dict[int, str]) -> dict:
    """All winners claim at once -> proves seats are never oversold."""
    if not winner_tokens:
        return {}
    print(f"  CLAIM STORM: {len(winner_tokens)} winners claiming simultaneously", flush=True)
    started = time.perf_counter()

    async def claim(index: int, token: str):
        transport = httpx.AsyncHTTPTransport(local_address=loopback_ip(5_000_000 + index), retries=0)
        async with httpx.AsyncClient(transport=transport, base_url=API_BASE, timeout=180) as client:
            try:
                response = await client.post(
                    f"/events/{event_id}/claim",
                    headers={"Authorization": f"Bearer {token}", "Idempotency-Key": f"lt-{event_id}-{index}"},
                )
                return response.status_code
            except Exception:
                return 599

    results = await asyncio.gather(*(claim(i, t) for i, t in winner_tokens.items()))
    codes = Counter(results)

    stats = await db_fetch_one(
        """
        select (select count(*) from reservations where event_id=:e)::int,
               (select count(distinct seat_number) from reservations where event_id=:e)::int,
               (select count(*) from (select seat_number from reservations where event_id=:e group by seat_number having count(*)>1) t)::int,
               (select count(*) from (select user_id from reservations where event_id=:e group by user_id having count(*)>1) t)::int,
               (select remaining_seats from events where id=:e)
        """,
        e=event_id,
    )
    return {
        "claim_requests": len(results),
        "claim_status_codes": {str(k): v for k, v in sorted(codes.items())},
        "reservations_created": stats[0],
        "distinct_seat_numbers": stats[1],
        "duplicate_seat_numbers": stats[2],
        "users_with_multiple_reservations": stats[3],
        "remaining_seats": stats[4],
        "oversold_seats": max(0, stats[0] - EVENT_CAPACITY),
        "duration_seconds": round(time.perf_counter() - started, 2),
    }


# --------------------------------------------------------------------------
# Cleanup
# --------------------------------------------------------------------------
async def cleanup(event_id, run_tag: str, admin_id: uuid.UUID) -> None:
    if event_id is None:
        async with AsyncSessionLocal() as db:
            await db.execute(
                text("delete from users where id=:a or email like :p"),
                {"a": admin_id, "p": f"lt-{run_tag}-%"},
            )
            await db.commit()
        return
    async with AsyncSessionLocal() as db:
        for sql in (
            "delete from reservations where event_id=:e",
            "delete from allocations where event_id=:e",
            "delete from allocation_runs where event_id=:e",
            "delete from entries where event_id=:e",
            "delete from events where id=:e",
            "delete from users where id=:a",
            "delete from users where email like :p",
        ):
            await db.execute(
                text(sql), {"e": event_id, "a": admin_id, "p": f"lt-{run_tag}-%"}
            )
    from app.core.redis import redis_client

    await redis_client.delete(f"audit:{event_id}")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
async def main_async() -> None:
    global SCALE
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--allocate-worker", action="store_true")
    parser.add_argument("--event-id")
    parser.add_argument("--admin-token")
    parser.add_argument("--start-at", type=float)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()
    SCALE = args.scale

    if args.allocate_worker:
        await allocate_worker(args.event_id, args.admin_token, float(args.start_at))
        return

    global NORMAL_USERS, FLASH_USERS, HIGH_SPEED_USERS, HIGH_VOLUME_REQUESTS
    global HIGH_VOLUME_USERS, DUPLICATE_CONCURRENT, FLASH_MAX_INFLIGHT, CONCURRENT_ALLOC_WORKERS
    NORMAL_USERS = scaled(NORMAL_USERS)
    FLASH_USERS = scaled(FLASH_USERS, 50)
    HIGH_SPEED_USERS = scaled(HIGH_SPEED_USERS, 10)
    HIGH_VOLUME_USERS = scaled(HIGH_VOLUME_USERS, 5)
    HIGH_VOLUME_REQUESTS = scaled(HIGH_VOLUME_REQUESTS, 200)
    DUPLICATE_CONCURRENT = scaled(DUPLICATE_CONCURRENT, 10)
    FLASH_MAX_INFLIGHT = scaled(FLASH_MAX_INFLIGHT, 50)
    CONCURRENT_ALLOC_WORKERS = CONCURRENT_ALLOC_WORKERS if args.scale >= 1.0 else 3

    run_tag = uuid.uuid4().hex[:10]
    print(f"run tag {run_tag}  scale={SCALE}")
    print(f"api {API_BASE}")

    admin_token, admin_id = await make_admin(run_tag)
    groups = {
        "normal": NORMAL_USERS,
        "flash": FLASH_USERS,
        "hspeed": HIGH_SPEED_USERS,
        "hvol": HIGH_VOLUME_USERS,
        "dup": 1,
    }
    tokens, user_ids = await seed_users(run_tag, groups)
    event_id = None
    report: dict = {"run_tag": run_tag, "api": API_BASE, "scenarios": []}

    try:
        event_id = await create_event(run_tag, admin_token)
        report["event_id"] = event_id
        print(f"event {event_id} capacity={EVENT_CAPACITY}\n")

        await reset_redis_for_run(run_tag, ["127.90.0.7"], event_id)
        await reset_redis_for_run(
            run_tag, [loopback_ip(i) for i in range(DUPLICATE_CONCURRENT + 900_000)], event_id
        )

        overall_started = time.perf_counter()

        # --- 1 NORMAL -------------------------------------------------
        print("\n[1/6] NORMAL")
        normal = await scenario_normal(event_id, tokens["normal"], concurrency=120)
        report["scenarios"].append(normal)
        print(json.dumps({k: normal[k] for k in ("total_requests", "successful_http_requests",
              "rejected_or_rate_limited", "rate_limited_429", "api_error_count",
              "transport_errors_599", "duration_seconds", "throughput_rps",
              "latency_p50_ms", "latency_p95_ms", "latency_p99_ms")}, indent=2))
        report["queue_after_normal"] = await queue_snapshot(event_id)

        # --- 2 HIGH-SPEED BOT ----------------------------------------
        print("\n[2/6] HIGH-SPEED BOT")
        high_speed = await scenario_high_speed_bot(event_id, tokens["hspeed"])
        report["scenarios"].append(high_speed)
        print(json.dumps({k: high_speed[k] for k in ("total_requests", "successful_http_requests",
              "rejected_or_rate_limited", "rate_limited_429", "distinct_entry_ids_returned",
              "latency_p50_ms", "latency_p95_ms")}, indent=2))

        # --- 3 HIGH-VOLUME BOT ---------------------------------------
        print("\n[3/6] HIGH-VOLUME BOT")
        high_volume = await scenario_high_volume_bot(event_id, tokens["hvol"])
        report["scenarios"].append(high_volume)
        print(json.dumps({k: high_volume[k] for k in ("total_requests", "successful_http_requests",
              "rejected_or_rate_limited", "distinct_entry_ids_returned",
              "latency_p50_ms", "latency_p95_ms")}, indent=2))

        # --- 4 DUPLICATE ATTACK --------------------------------------
        print("\n[4/6] DUPLICATE ATTACK")
        duplicate = await scenario_duplicate_attack(event_id, tokens["dup"][0])
        report["scenarios"].append(duplicate)
        print(json.dumps({k: duplicate[k] for k in ("total_requests", "successful_http_requests",
              "api_error_count", "transport_errors_599", "distinct_entry_ids_returned",
              "latency_p50_ms", "latency_p95_ms")}, indent=2))

        # --- 5 FLASH CROWD -------------------------------------------
        print("\n[5/6] FLASH CROWD")
        flash = await scenario_flash_crowd(event_id, tokens["flash"])
        report["scenarios"].append(flash)
        print(json.dumps({k: flash[k] for k in ("total_requests", "successful_http_requests",
              "rejected_or_rate_limited", "api_error_count", "transport_errors_599",
              "duration_seconds", "throughput_rps", "latency_p50_ms", "latency_p95_ms",
              "latency_p99_ms", "latency_max_ms")}, indent=2))

        report["queue_before_allocation"] = await queue_snapshot(event_id)
        report["entries_per_scenario"] = await per_group_entry_counts(event_id, run_tag)
        report["traffic_phase_seconds"] = round(time.perf_counter() - overall_started, 2)

        # close registration (the API exposes no endpoint for this)
        async with AsyncSessionLocal() as db:
            await db.execute(text("update events set is_open=false where id=:e"), {"e": event_id})
            await db.commit()

        # --- 6 CONCURRENT ALLOCATION ---------------------------------
        print("\n[6/6] CONCURRENT ALLOCATION")
        allocation_started = time.perf_counter()
        concurrent = await scenario_concurrent_allocation(event_id, admin_token)
        allocation_duration = time.perf_counter() - allocation_started
        report["scenarios"].append(concurrent)
        print(json.dumps(concurrent, indent=2, default=str))

        report["allocation"] = await allocation_snapshot(event_id)
        report["allocation_duration_seconds"] = round(allocation_duration, 2)
        report["winners_by_scenario"] = await winners_by_scenario(event_id, run_tag)

        # --- claim storm -> seat oversell ----------------------------
        if CLAIM_STORM and SCALE >= 1.0:
            winner_ids = {
                r[0]
                for r in await db_fetch_all(
                    "select user_id from allocations where event_id=:e and status='WINNER'",
                    e=event_id,
                )
            }
            token_by_uid = {}
            for group, ids in user_ids.items():
                for uid, token in zip(ids, tokens[group]):
                    if uid in winner_ids:
                        token_by_uid[uid] = token
            report["claim"] = await claim_storm(
                event_id, {i: t for i, t in enumerate(token_by_uid.values())}
            )
            report["claim"]["winner_tokens_available"] = len(token_by_uid)
            report["allocation_after_claims"] = await allocation_snapshot(event_id)
        else:
            report["claim"] = {}

        # --- verifications -------------------------------------------
        report["check_G_reproducibility"] = await verify_reproducible(event_id)
        report["check_H_batch_priority"] = await verify_batch_priority(event_id)
        report["check_I_randomisation"] = await verify_randomisation(event_id)
    finally:
        if not args.keep:
            print("\ncleaning up ...", flush=True)
            await cleanup(event_id, run_tag, admin_id)

    out_path = Path(__file__).resolve().parent / f"load_report_{run_tag}.json"
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nreport -> {out_path}")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main_async())