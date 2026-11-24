"""The Coach's knowledge base: reviewed-content entries loaded from
backend/content/kb/*.json, searched with a small BM25 (no external services).

The Coach answers ONLY from what this returns. If nothing scores above the
relevance threshold, the Coach says it doesn't have that information rather
than letting the model guess. Every entry carries a citation (`source`) and a
`reviewed` flag that stays false until the nutrition team approves it.
"""
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

KB_DIR = Path(__file__).parent / "content" / "kb"
REQUIRED = ("id", "title", "topic", "hei_component", "curriculum_area", "text", "source", "reviewed")
CURRICULUM_AREAS = {None, "planning", "applying", "assembling"}

_STOP = set("""a an and are as at be but by can do does for from how i if in into is it its me my of on or so
that the their them then there these this to too up us was we what when where which who why will with you your
i'm im it's its should could would get got any some much many more most just about ok okay hi hey please tell""".split())


def _stem(word: str) -> str:
    for suffix in ("ies", "es", "s"):
        if len(word) > 4 and word.endswith(suffix):
            return word[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return word


def tokenize(text: str) -> List[str]:
    words = re.findall(r"[a-z]+", text.lower().replace("fibre", "fiber"))
    return [_stem(w) for w in words if w not in _STOP and len(w) > 1]


def load_entries(kb_dir: Path = KB_DIR) -> List[dict]:
    entries: List[dict] = []
    for path in sorted(kb_dir.glob("*.json")):
        for e in json.loads(path.read_text()):
            missing = [k for k in REQUIRED if k not in e]
            if missing:
                raise ValueError(f"{path.name}: entry {e.get('id')} is missing {missing}")
            if not e["source"].strip():
                raise ValueError(f"{path.name}: entry {e['id']} needs a source citation")
            if e["curriculum_area"] not in CURRICULUM_AREAS:
                raise ValueError(f"{path.name}: entry {e['id']} has unknown curriculum_area")
            entries.append(e)
    ids = [e["id"] for e in entries]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate knowledge-base ids")
    return entries


class KnowledgeBase:
    """BM25 over title (weighted), tags (weighted) and text."""

    K1, B = 1.4, 0.75
    MIN_SCORE = 3.5  # below this, treat as "nothing relevant"

    def __init__(self, entries: List[dict]):
        self.entries = entries
        self.docs = [
            tokenize(e["title"]) * 3 + tokenize(" ".join(e.get("tags", []))) * 2 + tokenize(e["text"])
            for e in entries
        ]
        self.tf = [Counter(d) for d in self.docs]
        self.avgdl = sum(len(d) for d in self.docs) / max(1, len(self.docs))
        df = Counter(t for d in self.docs for t in set(d))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self.by_id = {e["id"]: e for e in entries}

    def score(self, query: str) -> List[tuple]:
        terms = tokenize(query)
        # Two-word phrases ("whole grain", "dining hall") get a bonus.
        q_low = query.lower().replace("fibre", "fiber")
        scored = []
        for i, e in enumerate(self.entries):
            tf, dl = self.tf[i], len(self.docs[i])
            s = 0.0
            for t in terms:
                f = tf.get(t, 0)
                if f:
                    s += self.idf.get(t, 0) * f * (self.K1 + 1) / (f + self.K1 * (1 - self.B + self.B * dl / self.avgdl))
            for tag in e.get("tags", []):
                if " " in tag and tag in q_low:
                    s += 2.0
            if s > 0:
                scored.append((s, e))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored

    def retrieve(self, query: str, k: int = 3) -> List[dict]:
        """Top-k relevant entries, or [] when nothing is relevant enough."""
        scored = self.score(query)
        if not scored or scored[0][0] < self.MIN_SCORE:
            return []
        top = scored[0][0]
        return [e for s, e in scored[:k] if s >= max(self.MIN_SCORE, top * 0.35)]

    def get(self, entry_id: str) -> Optional[dict]:
        return self.by_id.get(entry_id)


# ---- Scope: what the Coach politely declines ------------------------------
#
# Nutrition team 2026-11-06, Follow-ups item 2 ("Topics Future Me should not
# answer"). The six topics are detected here and the LLM is bypassed —
# Future Me replies verbatim with the matching REDIRECT text loaded from
# ``backend/content/future_me_redirects.json``. The topic names here
# (``medical``, ``medications``, ``eating_support``, ``weight``,
# ``calories``, ``specialized_diets``, ``urgent``) are the keys into that
# content file, so the team can rewrite any single redirect without a
# code change.

# Topic A — Diagnosis, treatment, or condition-specific dietary advice.
# Deliberately NARROWER than before: medications / supplements words
# moved to _MEDICATIONS so the right redirect fires for "should I take a
# multivitamin?" (not the medical one).
_MEDICAL = re.compile(
    r"\b(diagnos\w*|disease|diabet\w*|cholesterol|high blood pressure|hypertension|celiac|"
    r"crohn\w*|ibs|gerd|reflux|thyroid|pcos|lupus|"
    r"doctor|clinic\w*|allerg(y|ic) test|pregnan\w*|treat(ment)?|cure|heart attack)\b",
    re.IGNORECASE,
)

# Topic B — Medications and supplements (use, effectiveness, safety,
# dosing, interactions). New in 2026-11-06.
_MEDICATIONS = re.compile(
    r"\b(medication\w*|medicine\w*|prescri\w*|pill\w*|"
    r"supplement\w*|vitamin\s+(pill|supplement|c|d|b12|b6|iron|zinc|magnesium)|"
    r"fish oil|omega.?3\s+pill|protein powder|creatine|"
    r"multivit\w*|probiotic\w*|collagen|melatonin|"
    r"metformin|ozempic|wegovy|statin\w*|antidepressant\w*)\b",
    re.IGNORECASE,
)

_WEIGHT = re.compile(
    r"\b(lose|losing|lost)\s+(weight|\d+\s*(lbs?|pounds?|kg|kilos?))\b|"
    # Allow a hyphen between 'weight' and 'loss' / 'gain' ("weight-loss plan").
    r"\bweight[-\s]*(loss|gain)\b|"
    r"\bdrop\s+\d+\s*(lbs?|pounds?)\b|"
    r"\b(slim|thin|skinny|fat burn\w*|burn fat|bmi|body fat|"
    r"diet to|cutting|bulk(ing)?|how much should i weigh|weigh myself|"
    r"calorie deficit|calorie\s+(target|goal|limit))\b",
    re.IGNORECASE,
)

# Topic E — Specialised diets (keto, detox, fasting, other restrictive
# or therapeutic diets). New in 2026-11-06.
_SPECIALIZED_DIETS = re.compile(
    r"\b(keto(genic)?|low[-\s]?carb\s+diet|atkins|paleo|whole30|"
    r"detox(ing|ify|ification)?|cleanse|juice\s+cleanse|master\s+cleanse|"
    r"fasting|fasted|intermittent\s+fasting|water\s+fast\w*|extended\s+fast\w*|"
    r"carnivore\s+diet|zone\s+diet|dukan|optavia|noom|"
    r"low\s*fodmap|elimination\s+diet|gaps\s+diet|anti.?inflammatory\s+diet)\b",
    re.IGNORECASE,
)

# Topic F — Urgent / emergency health concerns. New in 2026-11-06. Matches
# BEFORE the broader medical bucket in scope_check() so a student
# reporting chest pain gets the 911 message, not the general redirect.
_URGENT = re.compile(
    r"\b(chest\s+pain|can'?t\s+breathe|trouble\s+breathing|short(ness)?\s+of\s+breath|"
    r"passing\s+out|passed\s+out|fainted?|unconscious|"
    r"allergic\s+reaction|anaphyla\w*|epipen|"
    r"overdose|poison\w*|swallowed\s+(poison|bleach|pills)|"
    r"severe\s+pain|severe\s+bleed\w*|heavy\s+bleed\w*|"
    r"suicid\w*|kill\s+myself|want\s+to\s+die|hurt\s+myself|self[-\s]harm\w*|"
    r"stroke|seizure|slurred\s+speech|numb\s+(arm|leg|face)|"
    r"9.?1.?1|emergency\s+room|er\s+(visit|right now))\b",
    re.IGNORECASE,
)
# Calorie-counting questions are declined, but general nutrient-amount
# questions ("how much sodium should I have?", "how many grams of fiber per
# day?", "how do I read a sodium label?") are now ALLOWED (nutrition team,
# 2026-10-29). The regex intentionally stays tight: 'calories', 'kcal',
# 'macros', and clear counting language — no 'grams of X' catch-all.
_CALORIE = re.compile(
    r"\b(calori\w*|kcal|macros?|counting\s+calories?|calorie\s+count\w*|how\s+many\s+calories|"
    r"how\s+few\s+calories|how\s+little\s+can\s+i\s+eat|eat\s+less\s+than\s+\d+)\b",
    re.IGNORECASE,
)

# Nutrition team feedback (2026-11-03): questions that signal
# restriction, meal-skipping, food-group elimination, or emotional
# distress around eating must route to a short supportive DECLINE that
# acknowledges the feeling and points at the study team + campus health
# — the Coach must NOT give the LLM a chance to produce restrictive
# advice here. Pattern list is deliberately broad; false positives land
# on the supportive reply, which is always safe.
_EATING_SUPPORT = re.compile(
    r"\b("
    r"stop\s+eating\s+(so\s+much|too\s+much)|"
    r"feel\s+guilty\s+after\s+eating|guilty\s+about\s+eating|"
    r"eating\s+too\s+much|can'?t\s+stop\s+eating|"
    r"binge|binging|bingeing|purge|purging|"
    r"starve|starving|not\s+eating|skipping\s+meals|skip\s+meals|"
    # Allow "skip" / "skipping" / "skipped" + meal + (to|and|for) so
    # "I keep skipping dinner to save calories" routes to eating_support.
    r"skipp?(?:ing|ed)?\s+(breakfast|lunch|dinner|dessert|snacks?)(\s+(to|and|for)|\b)|"
    r"should\s+i\s+skip\s+(breakfast|lunch|dinner|a\s+meal|meals)|"
    r"cut\s+out\s+(all|every|carbs?|fats?|grains?|dairy|sugar|fruit|protein)|"
    r"eliminate\s+(carbs?|fats?|grains?|dairy|sugar|fruit|protein|food\s+groups?)|"
    r"very\s+low\s+calor(ie|y)|extremely\s+low\s+calor|starvation\s+diet|crash\s+diet|"
    r"anorex\w*|bulim\w*|orthorex\w*|eating\s+disorder|"
    # Restriction-framed calorie questions: "how few calories",
    # "how little can I eat", "eat less than 1200". These sit in the
    # eating-support bucket (compassionate redirect) rather than the
    # generic calorie DECLINE — the question itself signals restriction
    # intent, not curiosity about targets.
    r"how\s+few\s+calories|how\s+little\s+can\s+i\s+eat|eat\s+less\s+than\s+\d+"
    r")\b",
    re.IGNORECASE,
)


def scope_check(question: str) -> Optional[str]:
    """Returns the matching scope-redirect topic, or None.

    Topics (nutrition team 2026-11-06, Follow-ups item 2):
    ``urgent`` | ``eating_support`` | ``weight`` | ``calories`` |
    ``specialized_diets`` | ``medications`` | ``medical``.

    The LLM is bypassed for every one of these — the matching entry in
    ``backend/content/future_me_redirects.json`` is what the student sees.

    Order matters: urgent fires before medical so a report of chest pain
    gets the 911 message; eating_support fires before weight so restriction
    questions get the compassionate referral; calories is a narrower
    weight-adjacent bucket for pure "how many calories?" questions.
    """
    if _URGENT.search(question):
        return "urgent"
    if _EATING_SUPPORT.search(question):
        return "eating_support"
    if _WEIGHT.search(question):
        return "weight"
    if _CALORIE.search(question):
        return "calories"
    if _SPECIALIZED_DIETS.search(question):
        return "specialized_diets"
    if _MEDICATIONS.search(question):
        return "medications"
    if _MEDICAL.search(question):
        return "medical"
    return None


# The redirect texts live in a content file so the nutrition team can
# rewrite any single topic without a code change. Keep in sync via the
# load_redirects() helper, which validates on startup. The ``DECLINE``
# name is kept as the public alias every caller already uses.

_REDIRECTS_PATH = Path(__file__).parent / "content" / "future_me_redirects.json"


def load_redirects(path: Path = _REDIRECTS_PATH) -> Dict[str, str]:
    """Load the topic -> student-facing text map. Every topic that
    ``scope_check`` can return must have an entry; missing entries
    fail loudly at import time so a typo doesn't ship a silent empty
    redirect to the student."""
    data = json.loads(path.read_text())
    topics = data.get("topics") or {}
    out = {name: (body or {}).get("text") or "" for name, body in topics.items()}
    required = {"urgent", "eating_support", "weight", "calories",
                "specialized_diets", "medications", "medical"}
    missing = required - set(out) | {k for k, v in out.items() if not v.strip() and k in required}
    if missing:
        raise ValueError(f"future_me_redirects.json is missing texts for: {sorted(missing)}")
    return out


def load_redirect_notes(path: Path = _REDIRECTS_PATH) -> List[str]:
    """Boundary notes the Future Me system prompt should include verbatim
    (e.g. "never diagnose", "study-team referrals")."""
    data = json.loads(path.read_text())
    notes = data.get("boundary_notes") or []
    return [n for n in notes if isinstance(n, str) and n.strip()]


DECLINE: Dict[str, str] = load_redirects()
BOUNDARY_NOTES: List[str] = load_redirect_notes()
# When no reviewed KB entry scores above the relevance threshold, Future Me
# tells the student plainly that the question is out of scope and offers
# a concrete redirect — no vague "I keep things additive" dodge.
NOT_FOUND = ("That one's outside what my reviewed notes cover, so the study team is the best place for a specific "
             "answer. I can help with food groups, dining-hall meals, label reading, planning, and budget swaps — "
             "ask me one of those and I'll give you a concrete suggestion.")
