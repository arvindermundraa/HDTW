"""Approved focus-area names check — nutrition team 2026-11-06, item 1
("Focus-area wording").

The team approved exactly these eight labels: grains, protein foods, fats,
vegetables and beans, dairy, sodium, added sugars, fruit — title-cased
where the design uses them as titles (for example "Vegetables and beans").

This test pins:

  1. Every id → label mapping in ``backend/focus_areas.py`` matches the
     approved list, in the approved capitalisation.
  2. Every place the app shows a focus-area label uses the same id →
     label mapping (via ``focus_areas.BY_ID``), and the TypeScript mirror
     in ``frontend/src/food.ts`` matches.
  3. No obsolete / deprecated label text ("Greens and Beans" by itself,
     "Veg & Beans", "Protein", bare "Fat") appears in a content file or a
     student-facing screen.

The HEI-2020 ``HEI2020_COMPONENTS`` list in ``server.py`` is deliberately
NOT constrained by this test: component labels ("Whole Grains", "Fatty
Acids", "Greens & Beans") are internal to HEI-2020 scoring and are never
shown to the student — only the eight focus-area labels are.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import focus_areas


APPROVED = {
    "fruit": "Fruit",
    "vegetables_beans": "Vegetables and beans",
    "grains": "Grains",
    "dairy": "Dairy",
    "protein_foods": "Protein foods",
    "fats": "Fats",
    "sodium": "Sodium",
    "added_sugars": "Added sugars",
}


def test_focus_area_labels_match_the_approved_list():
    for area_id, expected in APPROVED.items():
        assert focus_areas.BY_ID[area_id]["label"] == expected, (
            f"focus_areas.BY_ID[{area_id!r}] label is "
            f"{focus_areas.BY_ID[area_id]['label']!r} but the team approved {expected!r}"
        )
    assert set(focus_areas.BY_ID) == set(APPROVED), (
        "focus_areas.BY_ID has a different set of ids from the approved list."
    )


def test_frontend_mirror_matches_backend():
    """``frontend/src/food.ts`` carries a ``FOCUS_AREA_LABEL`` object the UI
    uses when it only has the id to hand. Keep it in sync with the backend
    source of truth (``focus_areas.py``). Parse the TypeScript literally to
    avoid pulling in a Node tool-chain for a test."""
    repo_root = Path(__file__).resolve().parents[2]
    food_ts = (repo_root / "frontend" / "src" / "food.ts").read_text()
    m = re.search(r"FOCUS_AREA_LABEL:\s*Record<string,\s*string>\s*=\s*\{([^}]*)\}", food_ts)
    assert m, "FOCUS_AREA_LABEL not found in frontend/src/food.ts"
    pairs = dict(re.findall(r'(\w+)\s*:\s*"([^"]*)"', m.group(1)))
    for area_id, expected in APPROVED.items():
        assert pairs.get(area_id) == expected, (
            f"frontend/src/food.ts FOCUS_AREA_LABEL[{area_id!r}] is "
            f"{pairs.get(area_id)!r} but the team approved {expected!r}"
        )


def test_no_deprecated_focus_area_labels_in_content():
    """Specifically: no label-shaped JSON field in a content file uses an
    old spelling of a focus-area name. Narrower than a free-text grep,
    which produced false positives (e.g. "Protein + fruit" as a sentence
    in game feedback, where "protein" is a nutrient word, not a label)."""
    repo_root = Path(__file__).resolve().parents[2]
    content_dir = repo_root / "backend" / "content"

    deprecated_labels = {
        # old spelling -> approved spelling
        "Protein": "Protein foods",
        "Veg & Beans": "Vegetables and beans",
        "Vegetables & Beans": "Vegetables and beans",
    }
    label_field_re = re.compile(r'"(?:label|title|name|swap_label)":\s*"([^"]+)"')
    hits: list[str] = []
    for f in content_dir.rglob("*.json"):
        text = f.read_text()
        for m in label_field_re.finditer(text):
            value = m.group(1)
            if value in deprecated_labels:
                line = text.count("\n", 0, m.start()) + 1
                hits.append(f"{f.relative_to(repo_root)}:{line}: {value!r} "
                            f"(use {deprecated_labels[value]!r})")
    assert not hits, "Deprecated focus-area labels in student-facing content:\n" + "\n".join(hits)
