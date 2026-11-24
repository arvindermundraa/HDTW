"""Produce 15 example "Plan Your Week" AI responses for the nutrition team
to review.

The Plan Your Week mini-game (``g1`` in ``backend/content/games.json``)
runs the student through 15 scenarios across three rounds: Sunday setup,
Weekday execution, and Budget and scale. Each scenario shows a prompt and
three choices. In the shipped app, the feedback per choice is scripted;
this script generates what a Future-Me-style AI response would look like
for each scenario and a chosen option, so the nutrition team can judge
whether to approve an AI-feedback variant later.

Usage (always from the repo root):

    ./backend/venv/bin/python backend/scripts/plan_your_week_ai_examples.py

* The TAMU AI key must be in ``backend/.env`` as ``TAMUS_API_KEY=sk-...``
  (or already set in the shell env). The script loads it via python-dotenv
  and NEVER prints it, logs it, or writes it to disk.
* Output: ``docs/nutrition_review/06_plan_your_week_ai_examples.md`` — a
  Markdown document with a one-row-per-scenario table of scenario,
  student's choice, and the real TAMU AI response.
* No backend server needs to be running; the script calls TAMU AI
  directly.

If TAMU AI can't be reached, the script writes a stub Markdown document
listing the 15 scenario+choice pairs with a blank "AI response" column
and exits non-zero. The one-line command above is what the team should
re-run when TAMU AI is reachable.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# Stand-alone: no FastAPI imports, just the TAMU client module.
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv  # type: ignore  # noqa: E402
import tamus_client  # noqa: E402


OUT_PATH = REPO_ROOT / "docs" / "nutrition_review" / "06_plan_your_week_ai_examples.md"
GAMES_PATH = BACKEND / "content" / "games.json"

# Pick one choice per scenario to showcase. Mix of "correct" (what the
# scripted rubric would call the strong pick) and "not correct" (a weaker
# pick), so the AI response is exercised across a spread.
CHOICE_SELECTIONS: Dict[str, str] = {
    "s1": "a",    # correct — flexible staples
    "s2": "a",    # correct — big batch of bases
    "s3": "c",    # weaker — order delivery because "boring"
    "s4": "b",    # strong pick (wherever it lands)
    "s5": "a",
    "s6": "c",    # weaker — "skip lunch"
    "s7": "b",
    "s8": "a",    # strong — pantry rescue
    "s9": "c",    # weaker — "cancel plans with friends"
    "s10": "b",
    "s11": "a",
    "s12": "c",   # weaker — "always fresh"
    "s13": "b",
    "s14": "a",
    "s15": "b",
}

# System prompt mirrors the Coach / Future Me tone — supportive,
# nonjudgmental, strengths-based, action-oriented, no numbers, no
# labeling foods as "good"/"bad." Reflects the nutrition team's 2026-11-06
# feedback (Scoring and Feedback, Q3).
SYSTEM_PROMPT = (
    "You are Future Me, the student's future self, speaking warmly in the first person. "
    "The student is in the Plan Your Week mini-game inside the LLHS app, a program for "
    "TAMU emerging adults (18–25). Each round, they see a scenario and pick one of three "
    "options. You give short, kind feedback on the option they picked, in at most two "
    "short sentences.\n\n"
    "Follow these rules in every response:\n"
    "- Be supportive, nonjudgmental, strengths-based and action-oriented.\n"
    '- Avoid: "unhealthy", "poor choices", "cheating", "should", "must", "not enough", '
    '"too much", "fix your diet", "you need to improve". Never label foods "good" or "bad".\n'
    '- Prefer: "You\'re making progress", "One area to build on", "An opportunity to try '
    'something different", "Consider adding…", "You might try…", "Small changes can add up".\n'
    '- For dietary feedback, use "Your recent meals suggest…" or "Based on the days you '
    'reported…" rather than definitive statements about someone\'s usual diet.\n'
    '- For setbacks, use "Progress isn\'t always consistent" or "What might work better for '
    'you next time?" rather than emphasizing failure.\n'
    "- Do not use any numbers, calories, grams, percentages or weight.\n"
    "- Do not give advice on medical conditions, medications/supplements, eating disorders, "
    "weight loss or calorie restriction, specialized diets (keto, detox, fasting), or "
    "urgent health concerns. Those are outside your scope.\n"
    "- Reply with the feedback text only — no greeting, no sign-off."
)


def _user_prompt(scenario_prompt: str, choice_text: str) -> str:
    return (
        f"Scenario: {scenario_prompt}\n"
        f"The student picked: \"{choice_text}\"\n"
        f"Write your feedback."
    )


def load_scenarios() -> List[Dict[str, Any]]:
    data = json.loads(GAMES_PATH.read_text())
    game = next(g for g in data["games"] if g["id"] == "g1")
    out: List[Dict[str, Any]] = []
    for r in game.get("rounds", []):
        for s in r.get("scenarios", []):
            out.append({
                "round_id": r["id"],
                "round_title": r["title"],
                "scenario_id": s["id"],
                "prompt": s["prompt"],
                "choices": s["choices"],
            })
    return out


async def _call_one(key: str, system: str, user_text: str) -> str:
    try:
        return await tamus_client.chat(
            key,
            tamus_client.DEFAULT_CHAT_MODEL,
            system,
            user_text,
            max_tokens=2048,
            temperature=0.0,
        )
    except tamus_client.TAMUSError as e:
        return f"[TAMU AI error — not shown to students]: {e}"


def _choice_for(scenario: Dict[str, Any]) -> Dict[str, Any]:
    sid = scenario["scenario_id"]
    target = CHOICE_SELECTIONS.get(sid, "a")
    for ch in scenario["choices"]:
        if ch["id"] == target:
            return ch
    return scenario["choices"][0]


async def main() -> int:
    load_dotenv(BACKEND / ".env")
    api_key_raw = os.environ.get("TAMUS_API_KEY", "")
    api_key = tamus_client.clean_api_key(api_key_raw)
    scenarios = load_scenarios()

    rows: List[Dict[str, Any]] = []
    unreachable = False
    for sc in scenarios:
        ch = _choice_for(sc)
        user_text = _user_prompt(sc["prompt"], ch["text"])
        if api_key:
            response = await _call_one(api_key, SYSTEM_PROMPT, user_text)
        else:
            response = "[TAMU AI not configured locally — re-run with TAMUS_API_KEY set.]"
            unreachable = True
        if response.startswith("[TAMU AI error"):
            unreachable = True
        rows.append({
            "round_id": sc["round_id"],
            "round_title": sc["round_title"],
            "scenario_id": sc["scenario_id"],
            "prompt": sc["prompt"],
            "choice_id": ch["id"],
            "choice_text": ch["text"],
            "ai_response": response.strip(),
        })

    render_markdown(rows, unreachable)
    return 1 if unreachable else 0


def _md_escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", "<br>")


def render_markdown(rows: List[Dict[str, Any]], unreachable: bool) -> None:
    lines: List[str] = []
    lines.append("# 6. Plan Your Week — 15 example AI responses\n\n")
    lines.append("**Source scenarios:** `backend/content/games.json`, game `g1`\n")
    lines.append("(Plan Your Week). **AI backend:** TAMU AI, default chat model, "
                 "run from this repo on ")
    lines.append(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC") + ".\n\n")
    lines.append("Context: The Plan Your Week mini-game has 15 scenarios across three "
                 "rounds (Sunday setup, Weekday execution, Budget and scale). In the "
                 "shipped app, each option has scripted feedback. The team asked (11/6, "
                 "Follow-ups, Q4) to see a set of example AI responses. The responses "
                 "below were generated by sending the scenario plus the student's chosen "
                 "option through TAMU AI with a Future-Me-style system prompt built from "
                 "the team's 2026-11-06 feedback (supportive, nonjudgmental, strengths-"
                 "based, action-oriented, no numbers, no good/bad food labels).\n\n")
    lines.append("All 15 AI responses below are marked **DRAFT** for team review.\n\n")
    if unreachable:
        lines.append("> **Note:** TAMU AI could not be reached for every scenario when "
                     "this file was generated. Re-run with:\n>\n"
                     "> `./backend/venv/bin/python backend/scripts/plan_your_week_ai_examples.py`\n>\n"
                     "> The script reads the TAMU AI key from `backend/.env` "
                     "(`TAMUS_API_KEY=...`) and never prints it.\n\n")
    current_round = None
    for i, row in enumerate(rows, start=1):
        if row["round_title"] != current_round:
            current_round = row["round_title"]
            lines.append(f"## {current_round}\n\n")
            lines.append("| # | Scenario | Student's choice | AI response (DRAFT) |\n")
            lines.append("|---|---|---|---|\n")
        lines.append(
            f"| {i} | {_md_escape(row['prompt'])} | "
            f"{_md_escape(row['choice_text'])} | "
            f"DRAFT — {_md_escape(row['ai_response'])} |\n"
        )
    lines.append("\n## How this was generated\n\n")
    lines.append("1. Load `backend/content/games.json`, pull every scenario in game `g1`.\n")
    lines.append("2. For each scenario, pick one of the three options (a spread of\n"
                 "   intended-strong and intended-weak picks).\n")
    lines.append("3. Build a system prompt from the nutrition team's 2026-11-06 feedback\n"
                 "   (Scoring and Feedback, Q3).\n")
    lines.append("4. Call TAMU AI (default chat model) with that system prompt plus the\n"
                 "   scenario and the student's chosen option.\n")
    lines.append("5. Write this Markdown file.\n\n")
    lines.append("No student records are used — the script does not read any Mongo\n"
                 "collection. The TAMU API key is loaded from `backend/.env` and never\n"
                 "printed or persisted.\n")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text("".join(lines))
    print(f"wrote {OUT_PATH.relative_to(REPO_ROOT)} ({len(rows)} rows)")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
