"""Generates the game screen's 8-bit sound effects as short, deterministic
mono WAV files — all CC0, authored here with no external audio sources.

Why generate instead of ship pre-recorded WAVs: the design calls for CC0
chiptune blips (jsfxr-style). Doing it in code keeps every sound exactly
reproducible, every character of its waveform reviewable in source control,
and the licence story clean.

The envelope rules match the spec:
  - Each sound is <1s.
  - "Not quite" is a soft descending blip, never a buzzer.
  - "Correct" is a short major arpeggio.
  - "Round complete" and "Game complete" are richer arpeggios, still <1s.
  - No random variation — same event, same sound, always.

Run from this directory:
    python3 generate_sfx.py
"""
import math
import struct
import wave
from pathlib import Path

SAMPLE_RATE = 22050
HERE = Path(__file__).parent


def square(freq: float, t: float) -> float:
    """8-bit style square wave at `freq` Hz, sampled at time `t` (sec)."""
    return 1.0 if math.sin(2 * math.pi * freq * t) >= 0 else -1.0


def env(t: float, dur: float, attack: float = 0.005, release: float = 0.03) -> float:
    """Attack-sustain-release envelope so blips don't click on edges."""
    if t < attack:
        return t / attack
    if t > dur - release:
        return max(0.0, (dur - t) / release)
    return 1.0


def tone(freq: float, dur: float, volume: float = 0.35) -> list:
    """A single square-wave tone with its own envelope."""
    n = int(SAMPLE_RATE * dur)
    out = []
    for i in range(n):
        t = i / SAMPLE_RATE
        v = square(freq, t) * env(t, dur) * volume
        out.append(v)
    return out


def sequence(notes: list, gap: float = 0.0) -> list:
    """Concatenate (freq, duration) tones with an optional silent gap."""
    out = []
    for freq, dur in notes:
        out.extend(tone(freq, dur))
        if gap > 0:
            out.extend([0.0] * int(SAMPLE_RATE * gap))
    return out


def write_wav(samples: list, filename: str) -> None:
    """Write 8-bit mono PCM — authentically chiptune, tiny file."""
    path = HERE / filename
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)  # 8-bit
        w.setframerate(SAMPLE_RATE)
        frames = bytearray()
        for s in samples:
            # 8-bit PCM is unsigned, biased around 128.
            v = max(-1.0, min(1.0, s))
            frames.append(int(round(v * 100 + 128)))
        w.writeframes(bytes(frames))
    print(f"wrote {path} ({len(samples) / SAMPLE_RATE:.2f}s)")


def main() -> None:
    # Button tap — single short mid blip (0.06s).
    write_wav(tone(760, 0.06, 0.3), "tap.wav")

    # Correct — rising C5-E5-G5 major arpeggio (0.24s total).
    write_wav(sequence([(523, 0.08), (659, 0.08), (784, 0.08)]), "correct.wav")

    # Not-quite — soft two-tone descending blip A4-F4 (0.18s total). The
    # second tone is quieter and shorter so it never feels like a buzzer.
    write_wav(
        tone(440, 0.09, 0.25) + tone(349, 0.09, 0.2),
        "not-quite.wav",
    )

    # Round complete — four-note ascending arpeggio C5-E5-G5-C6 (0.32s).
    write_wav(sequence([(523, 0.08), (659, 0.08), (784, 0.08), (1047, 0.08)]), "round-complete.wav")

    # Game complete — six-note triumphant run C5-E5-G5-C6-E6-G6 (0.78s).
    write_wav(
        sequence([(523, 0.13), (659, 0.13), (784, 0.13), (1047, 0.13), (1319, 0.13), (1568, 0.13)]),
        "game-complete.wav",
    )


if __name__ == "__main__":
    main()
