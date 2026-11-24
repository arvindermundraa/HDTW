# Game assets — credits & licences

All assets in this directory are **CC0 / public domain** — either hand-drawn
or code-generated inside this repo. No external pack (Kenney, OpenGameArt,
etc.) is bundled; if we add one later, note it here with its licence.

## Pixel sprites

`sprites/*.svg` — 16-grid pixel-art SVGs, hand-drawn by the LLHS team.
Released under **CC0 1.0 (Public Domain Dedication)**.

| File | Depicts | Author | Licence |
|------|---------|--------|---------|
| `sprites/apple.svg` | Red apple with stem and leaf | LLHS team | CC0 |
| `sprites/carrot.svg` | Carrot with green tops | LLHS team | CC0 |
| `sprites/broccoli.svg` | Broccoli crown and stalk | LLHS team | CC0 |
| `sprites/egg.svg` | Whole shelled egg | LLHS team | CC0 |
| `sprites/rice-bowl.svg` | Blue bowl with rice | LLHS team | CC0 |
| `sprites/bread.svg` | Loaf cross-section with seeds | LLHS team | CC0 |
| `sprites/fish.svg` | Side-view fish | LLHS team | CC0 |
| `sprites/cheese.svg` | Wedge of cheese with holes | LLHS team | CC0 |
| `sprites/water.svg` | Glass of water | LLHS team | CC0 |
| `sprites/cookie.svg` | Chocolate-chip cookie | LLHS team | CC0 |
| `sprites/salad.svg` | Salad bowl with greens | LLHS team | CC0 |

Sprites are rendered nearest-neighbour (`imageRendering: pixelated` on web,
`expo-image contentFit="contain"` on native) so the 16-grid stays crisp
when scaled up.

## Sound effects

`sfx/*.wav` — short 8-bit chiptune blips, all **under 1 second**.
Generated deterministically by `sfx/generate_sfx.py` in this repo
(square-wave oscillator + attack/release envelope). Released under
**CC0 1.0 (Public Domain Dedication)**.

| File | Event | Length | Author | Licence |
|------|-------|--------|--------|---------|
| `sfx/tap.wav` | Button tap (every tap in a game) | 0.06s | LLHS team | CC0 |
| `sfx/correct.wav` | Correct answer (C5–E5–G5 arpeggio) | 0.24s | LLHS team | CC0 |
| `sfx/not-quite.wav` | Soft "not quite" blip (A4→F4, never a buzzer) | 0.18s | LLHS team | CC0 |
| `sfx/round-complete.wav` | Round complete (C5–E5–G5–C6 arpeggio) | 0.32s | LLHS team | CC0 |
| `sfx/game-complete.wav` | Game complete (C5–E5–G5–C6–E6–G6 run) | 0.78s | LLHS team | CC0 |

Each sound is **always the same for the same event** — no random
jingles, no slot-machine-style reward sounds. The script in
`sfx/generate_sfx.py` is the canonical source; regenerating it produces
byte-identical WAV files.

### Why we don't ship Kenney WAVs here (yet)

The spec called out Kenney.nl's interface/digital-audio packs as a valid
CC0 source. We generated our own because:

1. The code-generated WAVs are tiny (1–17 kB each).
2. They're reproducible from source; a code review can verify every
   waveform without listening to a binary.
3. There's one place (`generate_sfx.py`) to tweak the entire sonic
   identity.

If the nutrition / design team prefers Kenney's richer samples, drop the
`.wav` files into `sfx/` using the same filenames and add a row to the
table above with the licence line (Kenney's packs are CC0 as well).

## Fonts

The game screens use **Press Start 2P** (SIL Open Font Licence) via
`@expo-google-fonts/press-start-2p` for titles, scores, round numbers,
and buttons only. Questions, answers and explanations stay in Plus
Jakarta Sans for readability. The licence travels with the font package.
