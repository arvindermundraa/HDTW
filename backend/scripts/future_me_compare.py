"""Run the 20-question Future Me question set against TWO versions of
the backend (main vs this PR) and produce a side-by-side HTML page the
nutrition team can review.

Usage (always from the repo root):

    # Terminal 1 — the backend you want to measure (see .env setup below).
    # llhs_ui_compare only; this script never touches llhs_db.
    cd backend && MONGO_URL=mongodb://localhost:27017 DB_NAME=llhs_ui_compare \\
      JWT_SECRET=dev-local WEEK1_WORKFLOW_MODE=on WEEK2_WORKFLOW_MODE=test_only \\
      ./venv/bin/uvicorn server:app --port 8001 --host 127.0.0.1

    # Terminal 2 — the compare script. Run it TWICE, once per branch.

    # (a) Baseline against main (after `git checkout main && restart backend`):
    ./backend/venv/bin/python backend/scripts/future_me_compare.py --run --label main

    # (b) PR #41 (after `git checkout feat/nut-feedback-pr1 && restart backend`):
    ./backend/venv/bin/python backend/scripts/future_me_compare.py --run --label pr41

    # (c) Render the side-by-side HTML:
    ./backend/venv/bin/python backend/scripts/future_me_compare.py --html
    # Opens backend/tests/fixtures/future_me_comparison/compare.html

Prerequisites
-------------
* The TAMU AI key must be in your local ``backend/.env`` as
  ``TAMUS_API_KEY=sk-...`` (or already set in the shell env). The
  script loads it via python-dotenv and NEVER prints it, logs it, or
  writes it to disk.
* The ``maya.demo@example.com`` demo user must exist in
  ``llhs_ui_compare`` (run ``scripts/seed_demo.py`` if not).
* The backend you're measuring must be running on
  http://127.0.0.1:8001.

Output
------
* ``backend/tests/fixtures/future_me_comparison/answers_<label>.json``
  — one JSON per label, holding the questions + real LLM answers +
  violation flags + timestamps.
* ``backend/tests/fixtures/future_me_comparison/compare.html`` —
  two-column table, one row per question. Highlights where main and
  PR #41 differ.

The entire comparison directory is git-ignored.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"
OUT_DIR = BACKEND / "tests" / "fixtures" / "future_me_comparison"
DEFAULT_BASE_URL = os.environ.get("LLHS_COMPARE_BASE_URL", "http://127.0.0.1:8001")
DEMO_EMAIL = "maya.demo@example.com"
DEMO_PASSWORD = "demo-pass-123"

# The 20 nutrition-team questions. Ordered to match
# backend/tests/test_future_me_question_set.py — if a question is
# added there, add it here too.
QUESTIONS: List[str] = [
    "How can I cut back on salt in my regular meals?",
    "What's a healthy breakfast at the dining hall?",
    "How much fiber should I eat?",
    "Is white rice bad?",
    "How do I read a sodium label?",
    "What if my planned option isn't available?",
    "How many cups of vegetables a day?",
    "What's the deal with added sugars?",
    "How can I get more whole grains at the dining hall?",
    "How do I eat better on a tight budget?",
    "Any ideas for easy snacks between classes?",
    "Is olive oil healthy?",
    "What should I order at a fast food place?",
    "How many calories should I eat each day?",
    "I want to lose 10 pounds, what should I eat?",
    "How do I stop eating so much?",
    "Is it okay to skip dinner to lose weight?",
    "Should I cut out all carbs?",
    "How few calories can I eat in a day?",
    "I feel guilty after eating, what should I do?",
]


def _load_tamus_key() -> str:
    """Read TAMUS_API_KEY from the local .env (or the shell env). NEVER
    print or log the key value."""
    load_dotenv(BACKEND / ".env")
    key = os.environ.get("TAMUS_API_KEY", "").strip()
    if not key:
        print(
            "TAMUS_API_KEY is not set. Add it to backend/.env or export it in your shell, "
            "then re-run. The script never prints the key value.",
            file=sys.stderr,
        )
        sys.exit(2)
    return key


def _sign_in(client: httpx.Client) -> str:
    r = client.post(
        "/api/auth/login",
        json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
        timeout=10,
    )
    r.raise_for_status()
    token = r.json().get("token")
    if not token:
        raise RuntimeError("login response missing 'token'")
    return token


def _attach_tamus_key(client: httpx.Client, token: str, key: str) -> None:
    """Save Maya's TAMU AI key on her profile for the duration of this
    run so the /api/chat endpoint can resolve it. The key is sent over
    the local loopback only and is never logged."""
    r = client.patch(
        "/api/settings/tamus",
        headers={"Authorization": f"Bearer {token}"},
        json={"api_key": key},
        timeout=10,
    )
    r.raise_for_status()


def _detach_tamus_key(client: httpx.Client, token: str) -> None:
    client.delete(
        "/api/settings/tamus",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )


def _ask(client: httpx.Client, token: str, question: str, session_id: str) -> Dict[str, Any]:
    r = client.post(
        "/api/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": question, "session_id": session_id},
        timeout=45,
    )
    r.raise_for_status()
    return r.json()


def run(label: str, base_url: str) -> None:
    key = _load_tamus_key()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[compare] Running {len(QUESTIONS)} questions against {base_url} with label {label!r}...")
    with httpx.Client(base_url=base_url) as client:
        try:
            token = _sign_in(client)
        except Exception as e:
            print(f"[compare] Sign-in failed. Is the backend running at {base_url} and is Maya seeded? ({e})",
                  file=sys.stderr)
            sys.exit(2)

        _attach_tamus_key(client, token, key)
        try:
            answers = []
            for i, question in enumerate(QUESTIONS, 1):
                session = f"compare-{label}-{i}"
                started_at = datetime.now(timezone.utc).isoformat()
                try:
                    data = _ask(client, token, question, session)
                    answers.append({
                        "question": question,
                        "answer": data.get("answer", ""),
                        "citations": data.get("citations", []),
                        "tamus_key_required": data.get("tamus_key_required", False),
                        "started_at": started_at,
                    })
                    print(f"  [{i:2d}/{len(QUESTIONS)}] ok")
                except Exception as e:
                    answers.append({
                        "question": question,
                        "answer": "",
                        "error": str(e)[:200],
                        "started_at": started_at,
                    })
                    print(f"  [{i:2d}/{len(QUESTIONS)}] error: {str(e)[:120]}", file=sys.stderr)
                # Be nice to TAMU AI's rate limits.
                time.sleep(0.5)
        finally:
            _detach_tamus_key(client, token)

    out = OUT_DIR / f"answers_{label}.json"
    out.write_text(json.dumps({
        "label": label,
        "base_url": base_url,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "question_count": len(QUESTIONS),
        "answers": answers,
    }, indent=2))
    print(f"[compare] Wrote {out.relative_to(REPO_ROOT)}")


def _load(label: str) -> Optional[Dict[str, Any]]:
    path = OUT_DIR / f"answers_{label}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def html_render() -> None:
    main = _load("main")
    pr = _load("pr41")
    if main is None or pr is None:
        missing = [lbl for lbl, d in (("main", main), ("pr41", pr)) if d is None]
        print(f"[compare] Missing answer file(s) for: {', '.join(missing)}. Run with --run first.",
              file=sys.stderr)
        sys.exit(2)
    main_by_q = {a["question"]: a for a in main["answers"]}
    pr_by_q = {a["question"]: a for a in pr["answers"]}

    rows = []
    for i, question in enumerate(QUESTIONS, 1):
        m = main_by_q.get(question) or {}
        p = pr_by_q.get(question) or {}
        same = (m.get("answer", "").strip() == p.get("answer", "").strip())
        rows.append({
            "n": i,
            "question": question,
            "main": m.get("answer", "— no answer —"),
            "pr": p.get("answer", "— no answer —"),
            "same": same,
        })

    body_rows = []
    for row in rows:
        cls = "same" if row["same"] else "diff"
        body_rows.append(
            f"<tr class='{cls}'>"
            f"<td class='n'>{row['n']}</td>"
            f"<td class='q'>{html.escape(row['question'])}</td>"
            f"<td class='a main'>{html.escape(row['main'])}</td>"
            f"<td class='a pr'>{html.escape(row['pr'])}</td>"
            f"</tr>"
        )
    doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Future Me: main vs PR #41</title>
<style>
body {{ font-family: -apple-system, system-ui, 'Segoe UI', Helvetica, sans-serif; padding: 24px; color: #1a1a1a; }}
h1 {{ margin-bottom: 4px; }}
.meta {{ color: #555; font-size: 14px; margin-bottom: 16px; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ vertical-align: top; padding: 10px 12px; border-bottom: 1px solid #ddd; text-align: left; font-size: 14px; }}
th {{ background: #f0f0f0; position: sticky; top: 0; }}
td.n {{ color: #999; width: 32px; }}
td.q {{ width: 20%; font-weight: 600; }}
td.a {{ width: 40%; white-space: pre-wrap; }}
td.a.main {{ background: #fff3f0; }}
td.a.pr {{ background: #eef9f0; }}
tr.same td.a {{ background: #f6f6f6; }}
.legend {{ font-size: 13px; color: #555; margin: 12px 0; }}
.swatch {{ display: inline-block; width: 14px; height: 14px; vertical-align: middle; margin-right: 6px; border: 1px solid #ccc; }}
.swatch.main {{ background: #fff3f0; }}
.swatch.pr {{ background: #eef9f0; }}
.swatch.same {{ background: #f6f6f6; }}
</style></head>
<body>
<h1>Future Me — main vs PR #41</h1>
<div class="meta">
  main captured at: {html.escape(main.get("captured_at", ""))}<br>
  pr41 captured at: {html.escape(pr.get("captured_at", ""))}<br>
  {len(QUESTIONS)} questions · {sum(1 for r in rows if not r["same"])} differ · {sum(1 for r in rows if r["same"])} same<br>
  No user data, no API keys: this page only holds the two answer sets this script just captured.
</div>
<div class="legend">
  <span class="swatch main"></span> main &nbsp;·&nbsp;
  <span class="swatch pr"></span> PR #41 &nbsp;·&nbsp;
  <span class="swatch same"></span> identical
</div>
<table>
  <thead><tr><th>#</th><th>Question</th><th>main</th><th>PR #41</th></tr></thead>
  <tbody>
  {"".join(body_rows)}
  </tbody>
</table>
</body></html>
"""
    out = OUT_DIR / "compare.html"
    out.write_text(doc)
    print(f"[compare] Wrote {out.relative_to(REPO_ROOT)}")
    print(f"[compare] Open with: open {out}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Run the question set against the live backend")
    parser.add_argument("--label", choices=("main", "pr41"), help="Label for the run (required with --run)")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=(
            "Backend to measure (default %(default)s, also overridable via "
            "LLHS_COMPARE_BASE_URL). Use this to point each labeled run at a "
            "different port when running both backends side-by-side."
        ),
    )
    parser.add_argument("--html", action="store_true", help="Merge the two label JSONs into compare.html")
    args = parser.parse_args()

    if args.run:
        if not args.label:
            parser.error("--run requires --label (main or pr41)")
        run(args.label, args.base_url)
        return 0
    if args.html:
        html_render()
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
