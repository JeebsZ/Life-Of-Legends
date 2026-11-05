"""XP and leveling rules. Pure logic - no UI, no I/O - so it is fully unit-testable."""

from dataclasses import dataclass, field

BASE_XP = 100  # XP needed to go from level 1 to 2
GROWTH = 1.25  # each level needs 25% more XP than the last


def xp_for_level(level: int) -> int:
    """XP required to advance from `level` to `level + 1`."""
    if level < 1:
        raise ValueError("level starts at 1")
    return round(BASE_XP * GROWTH ** (level - 1))


def bar_steps(level: int, xp: int, amount: int) -> list[float]:
    """XP-bar fill targets for animating a gain of `amount`.

    Each 1.0 is a level boundary (fill up, then the bar resets to empty);
    the last value is where the bar comes to rest.
    """
    steps: list[float] = []
    xp += amount
    while xp >= xp_for_level(level):
        xp -= xp_for_level(level)
        level += 1
        steps.append(1.0)
    steps.append(xp / xp_for_level(level))
    return steps


@dataclass
class Quest:
    title: str
    xp: int
    stat: str = "general"  # e.g. health, mind, wealth, social
    done: bool = False


@dataclass
class Hero:
    name: str = "Legend"
    level: int = 1
    xp: int = 0  # XP inside the current level
    quests: list[Quest] = field(default_factory=list)

    @property
    def xp_to_next(self) -> int:
        return xp_for_level(self.level)

    def gain_xp(self, amount: int) -> int:
        """Add XP, rolling over into level-ups. Returns how many levels were gained."""
        if amount < 0:
            raise ValueError("XP gain cannot be negative")
        self.xp += amount
        gained = 0
        while self.xp >= self.xp_to_next:
            self.xp -= self.xp_to_next
            self.level += 1
            gained += 1
        return gained

    def complete(self, quest: Quest) -> int:
        """Mark a quest done and award its XP once. Returns levels gained."""
        if quest.done:
            return 0
        quest.done = True
        return self.gain_xp(quest.xp)
