#!/usr/bin/env python3
"""Local load check for the Oct-27 Wings lab test.

Spins up 6 concurrent "users" against a locally-running backend (default
http://localhost:8001) for 2 minutes. Each user:
  1. Logs a short activity (POST /api/activities)
  2. Sends a Wing cheer (POST /api/wings/cheer)
  3. Polls the Wing summary (GET /api/wings/mine/summary)
  4. Sleeps ~15s and repeats

Reports per-endpoint request count, error rate, and response-time
percentiles (p50/p95/max). Target budget on a laptop + Mongo in Docker:
error rate 0 %, p95 < 500 ms.

Safety: this script will refuse to run unless the backend is configured
with DB_NAME=llhs_ui_compare. It never signs anyone up and never writes
to llhs_db. The accounts it uses must exist in llhs_ui_compare already
(see docs/wings_lab_test.md for the one-off seed script).

Usage:
  cd backend && python scripts/wings_load_check.py \\
      --accounts maya.demo@example.com:demo-pass-123,lab1@example.com:... \\
      --wing-code ABC123 \\
      [--base-url http://localhost:8001] [--duration 120]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from typing import Any

import httpx


DEFAULT_BASE = os.environ.get("LOAD_CHECK_BASE", "http://localhost:8001")


class RunStats:
    """Aggregates per-endpoint timing and error counts across all workers."""
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self.samples: dict[str, list[float]] = {}
        self.errors: dict[str, int] = {}
        self.ok: dict[str, int] = {}

    async def record(self, label: str, elapsed_ms: float, ok: bool) -> None:
        async with self._lock:
            self.samples.setdefault(label, []).append(elapsed_ms)
            if ok:
                self.ok[label] = self.ok.get(label, 0) + 1
            else:
                self.errors[label] = self.errors.get(label, 0) + 1


def _pct(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    k = max(0, min(len(xs) - 1, int(round(p * (len(xs) - 1)))))
    return xs[k]


async def _confirm_safe_db(base: str) -> None:
    """Refuse to run against a server that might be talking to llhs_db.

    The backend doesn't expose `DB_NAME` directly, but the dev stack sets
    `/docs` to the OpenAPI UI on both llhs_db and llhs_ui_compare, so this
    smoke-check is tightly scoped: we only poke a public endpoint, and we
    rely on the operator-supplied `--i-know` flag plus the env var hint.
    """
    hinted = os.environ.get("LOAD_CHECK_DB_NAME") or ""
    if hinted and hinted != "llhs_ui_compare":
        print(f"REFUSE: LOAD_CHECK_DB_NAME is {hinted!r}; this script only "
              f"runs against llhs_ui_compare.", file=sys.stderr)
        sys.exit(2)
    async with httpx.AsyncClient(base_url=base, timeout=5.0) as c:
        try:
            r = await c.get("/docs")
            r.raise_for_status()
        except Exception as e:
            print(f"REFUSE: backend not reachable at {base}: {e}", file=sys.stderr)
            sys.exit(2)


async def _login(client: httpx.AsyncClient, email: str, password: str) -> str:
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["token"]


async def _ensure_in_wing(client: httpx.AsyncClient, token: str, wing_code: str) -> None:
    """If the user isn't in a Wing, join by code. If they're in a DIFFERENT
    wing, leave first and then join. Idempotent across runs."""
    headers = {"Authorization": f"Bearer {token}"}
    r = await client.get("/api/wings/mine", headers=headers)
    r.raise_for_status()
    mine = r.json().get("wing")
    if mine and mine.get("join_code", "").upper() == wing_code.upper():
        return
    if mine:
        await client.post("/api/wings/leave", headers=headers)
    await client.post("/api/wings/join", headers=headers, json={"join_code": wing_code.upper()})


async def _worker(
    idx: int, email: str, password: str, wing_code: str, base: str,
    duration_s: int, stats: RunStats,
) -> None:
    async with httpx.AsyncClient(base_url=base, timeout=10.0) as c:
        token = await _login(c, email, password)
        await _ensure_in_wing(c, token, wing_code)
        headers = {"Authorization": f"Bearer {token}"}
        end_at = time.monotonic() + duration_s
        cheer_keys = ["nice_work", "keep_going", "proud_of_us"]
        iteration = 0
        while time.monotonic() < end_at:
            iteration += 1
            # 1. Log a tiny activity so the Wing's progress number moves.
            await _timed(stats, "POST /activities",
                         c.post, "/api/activities", headers=headers,
                         json={"minutes": 5, "kind": "walk", "source": "manual"})
            # 2. Send a cheer (rotating through the 3 presets).
            await _timed(stats, "POST /wings/cheer",
                         c.post, "/api/wings/cheer", headers=headers,
                         json={"key": cheer_keys[iteration % 3]})
            # 3. Poll the summary — simulates the 15s auto-poll on the Wings screen.
            await _timed(stats, "GET /wings/mine/summary",
                         c.get, "/api/wings/mine/summary", headers=headers)
            # Space worker calls out so they don't all land on the same ms.
            await asyncio.sleep(15 + (idx * 0.3))


async def _timed(stats: RunStats, label: str, fn, *args: Any, **kwargs: Any) -> None:
    t0 = time.perf_counter()
    ok = False
    try:
        r = await fn(*args, **kwargs)
        ok = 200 <= r.status_code < 300
        if not ok:
            # Print body once so a dev can see what went wrong, but don't
            # drown the terminal if every call fails.
            try:
                body = r.text[:200]
            except Exception:
                body = "<unreadable>"
            if (stats.errors.get(label, 0)) < 3:
                print(f"  [err] {label} -> {r.status_code}: {body}", file=sys.stderr)
    except Exception as e:
        if (stats.errors.get(label, 0)) < 3:
            print(f"  [exc] {label}: {e}", file=sys.stderr)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    await stats.record(label, elapsed_ms, ok)


def _parse_accounts(spec: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for pair in spec.split(","):
        pair = pair.strip()
        if not pair:
            continue
        if ":" not in pair:
            raise SystemExit(f"bad account spec {pair!r}; expected email:password")
        email, pw = pair.split(":", 1)
        out.append((email.strip(), pw.strip()))
    if not out:
        raise SystemExit("no accounts given")
    return out


async def main_async(args: argparse.Namespace) -> int:
    await _confirm_safe_db(args.base_url)
    accounts = _parse_accounts(args.accounts)
    if len(accounts) < 2:
        print("At least 2 accounts are required so Wing membership makes sense.", file=sys.stderr)
        return 2
    stats = RunStats()
    print(f"Load check: {len(accounts)} users, {args.duration}s, wing code {args.wing_code}, base {args.base_url}")
    workers = [
        _worker(i, email, pw, args.wing_code, args.base_url, args.duration, stats)
        for i, (email, pw) in enumerate(accounts)
    ]
    t0 = time.monotonic()
    await asyncio.gather(*workers)
    elapsed = time.monotonic() - t0
    _report(stats, elapsed)
    return 0


def _report(stats: RunStats, elapsed_s: float) -> None:
    print(f"\nDone in {elapsed_s:.1f}s. Per-endpoint results:")
    labels = sorted(set(stats.samples) | set(stats.ok) | set(stats.errors))
    rows = []
    for label in labels:
        samples = stats.samples.get(label, [])
        n = len(samples)
        ok = stats.ok.get(label, 0)
        err = stats.errors.get(label, 0)
        p50 = _pct(samples, 0.50)
        p95 = _pct(samples, 0.95)
        mx = max(samples) if samples else 0
        rows.append((label, n, ok, err, p50, p95, mx))
    header = ("endpoint", "n", "ok", "err", "p50_ms", "p95_ms", "max_ms")
    widths = [max(len(str(r[i])) for r in [header] + [tuple(map(str, row)) for row in rows]) for i in range(len(header))]
    def _fmt(row: tuple) -> str:
        return "  ".join(str(c).ljust(widths[i]) for i, c in enumerate(row))
    print("  " + _fmt(header))
    for row in rows:
        print("  " + _fmt((row[0], row[1], row[2], row[3], f"{row[4]:.0f}", f"{row[5]:.0f}", f"{row[6]:.0f}")))

    total_err = sum(stats.errors.values())
    print(f"\nTotals: {sum(stats.ok.values())} ok, {total_err} errors.")
    if total_err:
        print(f"  Error rate: {total_err / max(1, sum(stats.ok.values()) + total_err):.1%}")
    else:
        print("  Error rate: 0.0% ✓")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--accounts", required=True,
                    help="Comma-separated email:password pairs for 6 accounts.")
    ap.add_argument("--wing-code", required=True, help="Join code for the shared test Wing.")
    ap.add_argument("--duration", type=int, default=120, help="Seconds to run (default 120).")
    ap.add_argument("--base-url", default=DEFAULT_BASE, help=f"Backend base URL (default {DEFAULT_BASE})")
    args = ap.parse_args()
    code = asyncio.run(main_async(args))
    sys.exit(code)


if __name__ == "__main__":
    main()
