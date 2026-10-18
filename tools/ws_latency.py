"""NFR-1 probe: 25 concurrent WebSocket clients on /ws/matches/{match_id}, p95 score-broadcast latency < 500 ms.

Usage: python tools/ws_latency.py [base_url] [rounds]
Each round posts one score event to POST /audit/v1/events and times, per client, the gap between the POST being
sent and that event's message arriving. Exit code 1 if p95 >= 500 ms or a client misses an event.
Leaves extra goals on match-m1: run POST /audit/v1/reset afterwards.
"""
import asyncio
import json
import sys
import time
import urllib.request
import uuid

import websockets

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8080"
ROUNDS = int(sys.argv[2]) if len(sys.argv) > 2 else 5
CLIENTS = 25
MATCH = "match-m1"
LIMIT_MS = 500.0
WAIT_S = 3.0


def post_event(event_id: str) -> int:
    body = json.dumps({"event_id": event_id, "match_id": MATCH, "type": "score",
                       "payload": {"team_id": "club-alpha-1", "event_type": "goal"}}).encode()
    req = urllib.request.Request(f"{BASE}/audit/v1/events", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status


async def wait_for(ws, event_id: str) -> float | None:
    deadline = time.perf_counter() + WAIT_S
    while (left := deadline - time.perf_counter()) > 0:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=left)
        except asyncio.TimeoutError:
            return None
        if event_id in raw:
            return time.perf_counter()
    return None


async def main() -> int:
    ws_url = BASE.replace("http", "ws", 1) + f"/ws/matches/{MATCH}"
    clients = [await websockets.connect(ws_url, open_timeout=5) for _ in range(CLIENTS)]
    for ws in clients:  # every client gets the snapshot first
        await asyncio.wait_for(ws.recv(), timeout=5)
    await asyncio.sleep(0.3)  # let every relay subscribe to pub/sub
    samples, missed = [], 0
    try:
        for _ in range(ROUNDS):
            eid = f"nfr1-{uuid.uuid4().hex[:12]}"
            waiters = [asyncio.create_task(wait_for(ws, eid)) for ws in clients]
            t0 = time.perf_counter()
            status = await asyncio.to_thread(post_event, eid)
            if status != 201:
                print(f"FAIL event POST returned {status}")
                return 1
            for got in await asyncio.gather(*waiters):
                if got is None:
                    missed += 1
                else:
                    samples.append((got - t0) * 1000)
            await asyncio.sleep(0.2)
    finally:
        for ws in clients:
            await ws.close()
    samples.sort()
    p95 = samples[max(0, int(round(0.95 * len(samples))) - 1)] if samples else float("inf")
    ok = missed == 0 and p95 < LIMIT_MS
    print(f"{'PASS' if ok else 'FAIL'} NFR-1: {CLIENTS} clients x {ROUNDS} events, {len(samples)} deliveries, "
          f"missed {missed}, p50 {samples[len(samples) // 2] if samples else 0:.1f} ms, p95 {p95:.1f} ms "
          f"(limit {LIMIT_MS:.0f} ms)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
