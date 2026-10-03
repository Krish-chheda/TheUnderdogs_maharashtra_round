"""Controlled localhost fairness and flash-crowd validation.

This harness calls the real FastAPI application and database. It uses ASGI
requests with virtual client addresses so the existing IP-based anti-bot and
rate-limit dependencies can be exercised without changing production code.
"""
import asyncio
import json
import sys
import time
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import delete, distinct, func, insert, select

asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token
from app.main import app
from app.models.base import Allocation, AllocationRun, Entry, Event, Reservation, User

API_EVENT_CAPACITY = 500
NORMAL_USERS = 50_000
FLASH_USERS = 5_000
CONCURRENCY = 15


def header_value(headers, name):
    for key, value in headers:
        if key.lower() == name.lower():
            return value.decode()
    return ""


async def asgi_request(method, path, token, client_ip, body=None):
    request_body = json.dumps(body).encode() if body is not None else b""
    headers = [
        (b"host", b"localhost:8000"),
        (b"user-agent", b"fairdrop-loadtest/1.0"),
        (b"authorization", f"Bearer {token}".encode()),
    ]
    if body is not None:
        headers.extend([(b"content-type", b"application/json"), (b"content-length", str(len(request_body)).encode())])
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers,
        "client": (client_ip, 50000),
        "server": ("localhost", 8000),
    }
    messages = []

    async def receive():
        return {"type": "http.request", "body": request_body, "more_body": False}

    async def send(message):
        messages.append(message)

    started = time.perf_counter()
    try:
        await app(scope, receive, send)
    except Exception as error:
        return {"status": 599, "body": {"error": type(error).__name__, "message": str(error)}, "latency_ms": (time.perf_counter() - started) * 1000}
    elapsed_ms = (time.perf_counter() - started) * 1000
    status = next(message["status"] for message in messages if message["type"] == "http.response.start")
    body_bytes = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    try:
        response_body = json.loads(body_bytes or b"{}")
    except json.JSONDecodeError:
        response_body = {"raw": body_bytes.decode(errors="replace")}
    return {"status": status, "body": response_body, "latency_ms": elapsed_ms}


async def run_requests(requests, concurrency=CONCURRENCY):
    semaphore = asyncio.Semaphore(concurrency)

    async def limited(request):
        async with semaphore:
            return await asgi_request(*request)

    started = time.perf_counter()
    responses = await asyncio.gather(*(limited(request) for request in requests))
    return responses, time.perf_counter() - started


async def seed_users(run_id, count):
    users = []
    tokens = []
    for index in range(count):
        user_id = uuid.uuid4()
        users.append({
            "id": user_id,
            "phone": f"9{run_id}{index}",
            "email": f"load-{run_id}-{index}@example.invalid",
            "password_hash": "load-test-only",
            "role": "user",
        })
        tokens.append(create_access_token({"sub": str(user_id), "role": "user"}))
    async with AsyncSessionLocal() as db:
        for start in range(0, len(users), 2000):
            await db.execute(insert(User), users[start : start + 2000])
        await db.commit()
    return users, tokens


async def create_test_event(run_id):
    now = datetime.now(timezone.utc)
    event = Event(
        name=f"Fairness Load Test {run_id}",
        capacity=API_EVENT_CAPACITY,
        remaining_seats=API_EVENT_CAPACITY,
        is_open=True,
        registration_start=now - timedelta(seconds=10),
        registration_deadline=now + timedelta(hours=1),
        event_date=now + timedelta(hours=2),
        batch_duration_seconds=2,
        batch_weights=[0.30, 0.25, 0.20, 0.15, 0.10],
        venue="localhost load test",
    )
    async with AsyncSessionLocal() as db:
        db.add(event)
        await db.commit()
        await db.refresh(event)
    return event.id


async def queue_counts(event_id):
    async with AsyncSessionLocal() as db:
        total, unique_users = (await db.execute(select(func.count(Entry.id), func.count(distinct(Entry.user_id))).where(Entry.event_id == event_id))).one()
        eligible = await db.scalar(select(func.count(Entry.id)).where(Entry.event_id == event_id, Entry.status == "ELIGIBLE"))
        return {"unique_queue_entries": unique_users, "queue_rows": total, "duplicate_queue_entries": total - unique_users, "eligible_entries": eligible or 0}


async def scenario(name, requests, event_id):
    responses, duration = await run_requests(requests)
    status_counts = Counter(response["status"] for response in responses)
    counts = await queue_counts(event_id)
    latencies = sorted(response["latency_ms"] for response in responses)
    return {
        "scenario": name,
        "total_requests": len(responses),
        "successful_http_requests": status_counts[200],
        "rejected_or_rate_limited": sum(status_counts[code] for code in (400, 401, 403, 409, 422, 429)),
        "api_error_count": sum(value for code, value in status_counts.items() if code >= 500),
        "unique_queue_entries": counts["unique_queue_entries"],
        "queue_rows": counts["queue_rows"],
        "duplicate_queue_entries": counts["duplicate_queue_entries"],
        "eligible_entries": counts["eligible_entries"],
        "duration_seconds": round(duration, 3),
        "p50_latency_ms": round(latencies[len(latencies) // 2], 2) if latencies else 0,
        "p95_latency_ms": round(latencies[int(len(latencies) * 0.95) - 1], 2) if latencies else 0,
        "status_codes": dict(status_counts),
    }


async def allocation_summary(event_id, admin_token):
    async with AsyncSessionLocal() as db:
        event = await db.get(Event, event_id)
        event.is_open = False
        await db.commit()
    requests = [("POST", f"/admin/events/{event_id}/allocate", admin_token, f"10.99.0.{index + 1}", None) for index in range(8)]
    started = time.perf_counter()
    responses, _ = await run_requests(requests, concurrency=8)
    duration = time.perf_counter() - started
    async with AsyncSessionLocal() as db:
        run_count = await db.scalar(select(func.count(AllocationRun.id)).where(AllocationRun.event_id == event_id))
        winner_count = await db.scalar(select(func.count(Allocation.id)).where(Allocation.event_id == event_id, Allocation.status == "WINNER"))
        waitlist_count = await db.scalar(select(func.count(Allocation.id)).where(Allocation.event_id == event_id, Allocation.status == "WAITLISTED"))
        duplicate_winners = await db.scalar(select(func.count(Allocation.user_id) - func.count(distinct(Allocation.user_id))).where(Allocation.event_id == event_id, Allocation.status == "WINNER"))
        winners_by_batch = dict((await db.execute(select(Entry.batch_id, func.count(Entry.id)).where(Entry.event_id == event_id, Entry.allocation_status == "WINNER").group_by(Entry.batch_id))).all())
    return {
        "concurrent_allocation_requests": len(responses),
        "allocation_http_200": sum(response["status"] == 200 for response in responses),
        "allocation_run_count": run_count,
        "winners": winner_count,
        "waitlist_count": waitlist_count,
        "duplicate_winners": duplicate_winners or 0,
        "oversold_seats": max(0, (winner_count or 0) - API_EVENT_CAPACITY),
        "winners_per_batch": winners_by_batch,
        "allocation_duration_seconds": round(duration, 3),
        "responses": [response["status"] for response in responses],
    }


async def cleanup(event_id, user_ids):
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Reservation).where(Reservation.event_id == event_id))
        await db.execute(delete(Allocation).where(Allocation.event_id == event_id))
        await db.execute(delete(AllocationRun).where(AllocationRun.event_id == event_id))
        await db.execute(delete(Entry).where(Entry.event_id == event_id))
        await db.execute(delete(Event).where(Event.id == event_id))
        await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()


async def main():
    run_id = uuid.uuid4().hex[:10]
    event_id = await create_test_event(run_id)
    users, tokens = await seed_users(run_id, NORMAL_USERS + FLASH_USERS)
    admin_id = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        await db.execute(insert(User).values(id=admin_id, email=f"admin-{run_id}@example.invalid", password_hash="load-test-only", role="admin"))
        await db.commit()
    admin_token = create_access_token({"sub": str(admin_id), "role": "admin"})

    try:
        normal_requests = [("POST", f"/events/{event_id}/join", tokens[index], f"10.0.{index // 250}.{index % 250 + 1}", None) for index in range(NORMAL_USERS)]
        reports = [await scenario("NORMAL", normal_requests, event_id)]

        high_speed_requests = [("POST", f"/events/{event_id}/join", tokens[index], f"10.20.{index // 250}.{index % 250 + 1}", None) for index in range(1000)]
        reports.append(await scenario("HIGH-SPEED BOT", high_speed_requests, event_id))

        high_volume_requests = [("POST", f"/events/{event_id}/join", tokens[index % 100], tokens[index % 100] and f"10.30.{index // 250}.{index % 250 + 1}", None) for index in range(2000)]
        reports.append(await scenario("HIGH-VOLUME BOT", high_volume_requests, event_id))

        duplicate_requests = [("POST", f"/events/{event_id}/join", tokens[0], f"10.40.{index // 250}.{index % 250 + 1}", None) for index in range(500)]
        reports.append(await scenario("DUPLICATE ATTACK", duplicate_requests, event_id))

        flash_start = NORMAL_USERS
        flash_requests = [("POST", f"/events/{event_id}/join", tokens[flash_start + index], f"10.50.{index // 250}.{index % 250 + 1}", None) for index in range(FLASH_USERS)]
        reports.append(await scenario("FLASH CROWD", flash_requests, event_id))

        allocation = await allocation_summary(event_id, admin_token)
        print(json.dumps({"event_id": str(event_id), "scenarios": reports, "allocation": allocation}, indent=2, default=str))
    finally:
        await cleanup(event_id, [user["id"] for user in users] + [admin_id])


if __name__ == "__main__":
    asyncio.run(main())
