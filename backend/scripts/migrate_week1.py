"""Pilot migration: pre-fill the weekly_workflow Week 1 record for
students who already completed the equivalent flow under program.py.

What this script does
---------------------
Eligible students: anyone with ``focus_area`` set AND ``focus_goal.goal``
AND ``focus_goal.plan``. These are the pilots who've been through the
current Week 1 (choose area + write goal + plan) — the whole point of
the migration is that they don't re-walk the new flow once the
``WEEK1_WORKFLOW_MODE`` flag flips to ``on``.

For each eligible student we upsert ``db.weekly_workflow`` with a Week
1 record where every step the student can't trivially replay is marked
``status=done`` at migration time:

  * overview_video, feedback, mini_lecture, reflection

Points are NOT re-awarded (``points_awarded_at_migration=0``) because
pilots already earned the equivalent points through program.py's
watch/practice/do_it/reflect steps. The engine's auto-complete rules
cover the remaining two steps:

  * focus_selection auto-completes from ``users.focus_area``
  * goal_and_plan auto-completes from ``users.focus_goal``

The record carries ``migrated: true`` so the research export can split
"finished Week 1 inside the app" from "finished Week 1 pre-migration".

Privacy
-------
* Terminal output and the dry-run JSON contain **last-4-chars of the
  user id, nothing else that identifies them** — no emails, no names.
* Goal and plan text is reported as a character count only.
* Dry-run artifacts land in ``backend/scripts/migrations/dry_runs/``
  (git-ignored).

Safety
------
* ``--dry-run`` is the default. ``--apply`` is required to write.
* ``--apply`` prints how many records would change and asks the
  operator to type ``YES`` before any write happens.
* Idempotent — re-running does nothing to students who already have a
  weekly_workflow Week 1 record (regardless of ``migrated`` flag).
* Refuses to run when ``DB_NAME`` is unset.

Usage
-----
    # Dry run against llhs_ui_compare (safe to re-run; nothing writes):
    DB_NAME=llhs_ui_compare python backend/scripts/migrate_week1.py

    # Dry run against production:
    DB_NAME=<prod-db-name> MONGO_URL=<prod-mongo-url> \\
      python backend/scripts/migrate_week1.py

    # Apply to production (prints the count and prompts for YES):
    DB_NAME=<prod-db-name> MONGO_URL=<prod-mongo-url> \\
      python backend/scripts/migrate_week1.py --apply
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
sys.path.insert(0, str(BACKEND))

from motor.motor_asyncio import AsyncIOMotorClient

# Steps the migration marks done at migration time (no points, no text
# content synthesised). ``focus_selection`` and ``goal_and_plan`` are
# left to the engine's auto-complete rules which read users.focus_area
# and users.focus_goal.
MIGRATED_STEPS = ("overview_video", "feedback", "mini_lecture", "reflection")
WEEK = 1

ARTIFACT_DIR = HERE / "migrations" / "dry_runs"


def _anon(user_id: str) -> str:
    """Opaque short id — the first 6 hex characters of SHA-256(user_id),
    prefixed to make it obvious the value is anonymised. Deterministic
    (same user ⇒ same anon id across runs, useful for diffing dry-runs)
    and non-reversible. Avoids leaking recognisable id tails (``demo-
    maya`` → ``maya``) when the operator pastes output into a review."""
    if not user_id:
        return "…------"
    return "…" + hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:6]


def _char_count(text) -> int:
    return len(text or "")


def _is_test_account_doc(u: dict) -> bool:
    """Mirror of server.is_test_account for pilots data — we re-implement
    the rule here rather than importing server.py so this script can be
    run against a prod database without loading the full FastAPI app."""
    email = (u.get("email") or "").strip().lower()
    if u.get("is_test_account"):
        return True
    if email.endswith("@example.com"):
        return True
    return False


async def _collect_rows(db) -> list[dict]:
    """One row per *eligible* student with everything the dry-run report
    (and the apply step) needs — no PII, just enough to decide whether
    to write."""
    rows: list[dict] = []
    users = db.users.find({}, {
        "_id": 0, "id": 1, "email": 1, "is_test_account": 1,
        "focus_area": 1, "focus_goal": 1,
    })
    async for u in users:
        focus_area = u.get("focus_area")
        goal_doc = u.get("focus_goal") or {}
        goal = (goal_doc.get("goal") or "").strip()
        plan = (goal_doc.get("plan") or "").strip()
        if not (focus_area and goal and plan):
            continue
        # Skip test accounts in production. For local demo migrations
        # the operator can override by setting ``INCLUDE_TEST=1``.
        if _is_test_account_doc(u) and not os.environ.get("INCLUDE_TEST"):
            continue
        existing = await db.weekly_workflow.find_one(
            {"user_id": u["id"], "week": WEEK}, {"_id": 0, "step_statuses": 1, "migrated": 1},
        )
        existing_steps = list((existing or {}).get("step_statuses", {}).keys())
        rows.append({
            "anon_id": _anon(u["id"]),
            "is_test": _is_test_account_doc(u),
            "focus_area": focus_area,
            "goal_chars": _char_count(goal),
            "plan_chars": _char_count(plan),
            "existing_record": bool(existing),
            "existing_step_count": len(existing_steps),
            "would_write_steps": [] if existing else list(MIGRATED_STEPS),
            "_user_id": u["id"],  # kept locally for the write step; stripped from the artifact
        })
    return rows


def _summary(rows: list[dict]) -> dict:
    to_write = [r for r in rows if not r["existing_record"]]
    skipped = [r for r in rows if r["existing_record"]]
    by_focus: dict[str, int] = {}
    for r in to_write:
        by_focus[r["focus_area"]] = by_focus.get(r["focus_area"], 0) + 1
    return {
        "eligible_total": len(rows),
        "would_write": len(to_write),
        "would_skip_existing": len(skipped),
        "by_focus_area": by_focus,
    }


def _print_table(rows: list[dict]) -> None:
    if not rows:
        print("  (no eligible rows)")
        return
    header = (
        f"  {'anon id':<8} {'is_test':<8} {'focus_area':<16} "
        f"{'goal_chars':<10} {'plan_chars':<10} {'existing':<9} {'would_write_steps'}"
    )
    print(header)
    print("  " + "-" * (len(header) - 2))
    for r in rows:
        print(
            f"  {r['anon_id']:<8} {str(r['is_test']):<8} {r['focus_area']:<16} "
            f"{r['goal_chars']:<10} {r['plan_chars']:<10} {str(r['existing_record']):<9} "
            f"{','.join(r['would_write_steps']) or '-'}"
        )


def _write_artifact(rows: list[dict], summary: dict, db_name: str) -> Path:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = ARTIFACT_DIR / f"migrate_week1_dry_run_{db_name}_{stamp}.json"
    anonymised = []
    for r in rows:
        anonymised.append({k: v for k, v in r.items() if not k.startswith("_")})
    out_path.write_text(json.dumps({"summary": summary, "rows": anonymised}, indent=2))
    return out_path


async def _apply(db, rows: list[dict], now_iso: str) -> int:
    """Upsert the Week 1 record for every eligible user without one. Each
    migrated step is written as ``status=done`` at migration time, with
    an explicit ``points_awarded_at_migration=0`` and a top-level
    ``migrated=true`` flag so the research export can tell migrated
    completions from in-app ones."""
    written = 0
    for r in rows:
        if r["existing_record"]:
            continue
        step_statuses = {
            sid: {
                "status": "done",
                "completed_at": now_iso,
                "points_awarded_at_migration": 0,
                "migrated": True,
            }
            for sid in MIGRATED_STEPS
        }
        key = {"user_id": r["_user_id"], "week": WEEK}
        await db.weekly_workflow.update_one(
            key,
            {
                "$set": {"step_statuses": step_statuses, "updated_at": now_iso, "migrated": True},
                "$setOnInsert": {**key, "created_at": now_iso},
            },
            upsert=True,
        )
        written += 1
    return written


async def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate Week 1 workflow records for pilots.")
    parser.add_argument("--apply", action="store_true", help="Actually write (requires typing YES).")
    args = parser.parse_args()

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        print("Set MONGO_URL and DB_NAME before running this script.", file=sys.stderr)
        return 2
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    rows = await _collect_rows(db)
    summary = _summary(rows)

    print(f"\nmigrate_week1  db={db_name}  include_test={bool(os.environ.get('INCLUDE_TEST'))}")
    print("--------------------------------------------------")
    print(f"  eligible total:        {summary['eligible_total']}")
    print(f"  would write:           {summary['would_write']}")
    print(f"  skip (already exists): {summary['would_skip_existing']}")
    if summary["by_focus_area"]:
        print(f"  by focus area:         {summary['by_focus_area']}")
    print()
    _print_table(rows)

    artifact = _write_artifact(rows, summary, db_name)
    print(f"\n  dry-run JSON written to {artifact.relative_to(BACKEND.parent)}")

    if not args.apply:
        print("\nDry run only. Re-run with --apply to write.")
        return 0

    if summary["would_write"] == 0:
        print("\nNothing to write. All eligible students already have a Week 1 record.")
        return 0

    print(
        f"\n{summary['would_write']} record(s) will be written to db={db_name!r}. "
        "No points will be awarded. Points are counted as already earned via program.py."
    )
    try:
        confirm = input("Type YES to continue, anything else to abort: ")
    except EOFError:
        confirm = ""
    if confirm.strip() != "YES":
        print("Aborted. Nothing written.")
        return 1

    now_iso = datetime.now(timezone.utc).isoformat()
    written = await _apply(db, rows, now_iso)
    print(f"\nWrote {written} record(s) at {now_iso}. Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
