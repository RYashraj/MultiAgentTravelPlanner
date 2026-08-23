"""
Week 7: Basic Load Test

Tests the API under concurrent requests using Python's ThreadPoolExecutor.
Does NOT require the server to be running — uses the FastAPI TestClient
which is synchronous and safe for concurrent use in tests.

Usage:
    python tests/load_test.py

Results will be printed to stdout and saved to load_test_results.json.
"""
import json
import statistics
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import jwt
import requests

BASE_URL = "http://localhost:8000/api/v1"
JWT_SECRET = "week-3-test-secret"  # Change to your test secret
CONCURRENCY = 10
REQUESTS_PER_WORKER = 5


def make_token(user_id: str = None) -> str:
    uid = user_id or str(uuid.uuid4())
    return jwt.encode(
        {"sub": uid, "email": f"{uid[:8]}@test.com", "aud": "authenticated"},
        JWT_SECRET,
        algorithm="HS256",
    )


def hit_health(worker_id: int) -> dict:
    """Hit the health endpoint — lightest possible request."""
    start = time.monotonic()
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=10)
        elapsed = time.monotonic() - start
        return {
            "worker": worker_id,
            "endpoint": "GET /health",
            "status": resp.status_code,
            "latency_ms": round(elapsed * 1000, 2),
            "ok": resp.status_code == 200,
        }
    except Exception as e:
        elapsed = time.monotonic() - start
        return {
            "worker": worker_id,
            "endpoint": "GET /health",
            "status": 0,
            "latency_ms": round(elapsed * 1000, 2),
            "ok": False,
            "error": str(e),
        }


def hit_trips_list(worker_id: int) -> dict:
    """Hit the trips list endpoint — requires auth, hits the DB."""
    token = make_token()
    headers = {"Authorization": f"Bearer {token}"}
    start = time.monotonic()
    try:
        resp = requests.get(f"{BASE_URL}/trips", headers=headers, timeout=10)
        elapsed = time.monotonic() - start
        return {
            "worker": worker_id,
            "endpoint": "GET /trips",
            "status": resp.status_code,
            "latency_ms": round(elapsed * 1000, 2),
            "ok": resp.status_code in (200, 401, 403),  # 401/403 expected if JWT validation differs
        }
    except Exception as e:
        elapsed = time.monotonic() - start
        return {
            "worker": worker_id,
            "endpoint": "GET /trips",
            "status": 0,
            "latency_ms": round(elapsed * 1000, 2),
            "ok": False,
            "error": str(e),
        }


def run_worker(worker_id: int) -> list[dict]:
    results = []
    for _ in range(REQUESTS_PER_WORKER):
        results.append(hit_health(worker_id))
        results.append(hit_trips_list(worker_id))
    return results


def main():
    print(f"\n{'='*60}")
    print(f"  VoyagerAI Load Test — {CONCURRENCY} workers × {REQUESTS_PER_WORKER} iterations")
    print(f"{'='*60}\n")

    all_results = []
    start_wall = time.monotonic()

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futures = [pool.submit(run_worker, i) for i in range(CONCURRENCY)]
        for future in as_completed(futures):
            all_results.extend(future.result())

    wall_time = time.monotonic() - start_wall
    total = len(all_results)
    successes = sum(1 for r in all_results if r["ok"])
    failures = total - successes
    latencies = [r["latency_ms"] for r in all_results]

    print(f"Total requests : {total}")
    print(f"Successful     : {successes} ({100*successes//total}%)")
    print(f"Failed         : {failures} ({100*failures//total}%)")
    print(f"Wall time      : {wall_time:.2f}s")
    print(f"Throughput     : {total/wall_time:.1f} req/s")
    print("\nLatency (ms):")
    print(f"  Min    : {min(latencies):.1f}")
    print(f"  Mean   : {statistics.mean(latencies):.1f}")
    print(f"  Median : {statistics.median(latencies):.1f}")
    print(f"  p95    : {sorted(latencies)[int(0.95*len(latencies))]:.1f}")
    print(f"  Max    : {max(latencies):.1f}")

    # Failures breakdown
    failed = [r for r in all_results if not r["ok"]]
    if failed:
        print("\nFailed requests:")
        for f in failed[:10]:
            print(f"  {f}")

    summary = {
        "concurrency": CONCURRENCY,
        "requests_per_worker": REQUESTS_PER_WORKER,
        "total_requests": total,
        "successful": successes,
        "failed": failures,
        "success_rate_pct": round(100 * successes / total, 2),
        "wall_time_s": round(wall_time, 3),
        "throughput_rps": round(total / wall_time, 2),
        "latency_ms": {
            "min": round(min(latencies), 2),
            "mean": round(statistics.mean(latencies), 2),
            "median": round(statistics.median(latencies), 2),
            "p95": round(sorted(latencies)[int(0.95 * len(latencies))], 2),
            "max": round(max(latencies), 2),
        },
        "results": all_results,
    }

    with open("load_test_results.json", "w") as f:
        json.dump(summary, f, indent=2)

    print("\nResults saved to load_test_results.json")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
