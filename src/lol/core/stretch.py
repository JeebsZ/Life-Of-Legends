"""Pre-run stretch guide (shown on the "stretch while a short ad plays" sheet, and on its own
for anyone). Gentle, static holds only: real value even without the ad. Plain data."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Stretch:
    id: str
    name: str
    how: str
    seconds: int  # hold time (per side when sides is True)
    sides: bool = True  # do it on each leg
    icon: str = "accessibility_new"  # Material icon name (the UI maps it)


STRETCHES: tuple[Stretch, ...] = (
    Stretch("calf", "Calf stretch",
            "Hands on a wall, one foot back, heel down. Lean in gently.", 20,
            icon="directions_walk"),
    Stretch("hamstring", "Hamstring stretch",
            "One heel forward on the ground, toes up. Hinge at the hips, back straight.", 20,
            icon="airline_seat_legroom_extra"),
    Stretch("quad", "Quad stretch",
            "Hold a wall, pull one foot toward your seat. Knees side by side.", 20,
            icon="accessibility_new"),
    Stretch("hip", "Hip flexor stretch",
            "Small lunge, back knee soft. Tuck your hips under until you feel the front.",
            20, icon="self_improvement"),
)
SAFETY = ("Gentle holds, no bouncing. A light pull is right; stop if anything hurts or feels "
          "sharp.")


def total_seconds(stretches: tuple[Stretch, ...] = STRETCHES) -> int:
    return sum(s.seconds * (2 if s.sides else 1) for s in stretches)
