"""Meal photo recognition boundary. Pure: no Flet, no network.

A recognizer turns a photo into food candidates. The engine plugs in as ONE class that
satisfies `Recognizer`; the meal screen gets it through a single swappable call and never
cares which engine it is. `ManualRecognizer` (the default) detects nothing, so the confirm
card opens with "pick foods" plus suggestions.

Contract (keep it stable):
    recognize(image_path: str) -> list[Candidate]
- `image_path`: a local file path to a JPEG/PNG (the screen writes camera bytes to a temp
  file first).
- Each Candidate: `name` (what the engine saw), `food_id` (a foods.py id, or None - the screen
  then matches `name` with foods.match_food), `confidence` 0..1, `portion_g_guess` (grams or
  None = use the food's typical portion).
- It may be slow (call it off the UI thread) and may raise; the screen treats an exception as
  "no detections".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

# confidence -> chip label (shown next to every kcal range)
CONFIDENCE_HIGH = 0.75
CONFIDENCE_MEDIUM = 0.45


@dataclass(frozen=True)
class Candidate:
    name: str
    confidence: float = 0.0  # 0..1
    food_id: str | None = None  # foods.py id (built-in or "cf<n>" custom), if the engine knows it
    portion_g_guess: float | None = None  # None = the food's typical portion


@runtime_checkable
class Recognizer(Protocol):
    name: str  # short label for the UI, e.g. "Manual", "On-device"

    def recognize(self, image_path: str) -> list[Candidate]: ...


class ManualRecognizer:
    """The default: no engine, no detections. The user picks foods themselves."""

    name = "Manual"

    def recognize(self, image_path: str) -> list[Candidate]:
        return []


def confidence_label(confidence: float | None) -> str:
    """'high' | 'medium' | 'low' for a 0..1 confidence (None = 'low')."""
    if confidence is None:
        return "low"
    if confidence >= CONFIDENCE_HIGH:
        return "high"
    if confidence >= CONFIDENCE_MEDIUM:
        return "medium"
    return "low"
