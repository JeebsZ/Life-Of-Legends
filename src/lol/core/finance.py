"""Core engine & models for Expense Tracking, Receipt Scanning, and Split Bills (Splitwise-style).

Belongs to the Steward Path (Path of Wealth & Financial Discipline).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

EXPENSE_CATEGORIES = (
    "Food & Dining",
    "Groceries",
    "Transportation",
    "Shopping",
    "Entertainment",
    "Utilities",
    "Health",
    "Other",
)

CATEGORY_ICONS: dict[str, str] = {
    "Food & Dining": "restaurant",
    "Groceries": "shopping_cart",
    "Transportation": "directions_car",
    "Shopping": "shopping_bag",
    "Entertainment": "movie",
    "Utilities": "receipt",
    "Health": "favorite",
    "Other": "more_horiz",
}


@dataclass
class ExpenseEntry:
    """A logged variable expense (manual or from receipt OCR)."""

    id: str
    title: str
    amount: float
    category: str = "Food & Dining"
    date: str = ""  # ISO "YYYY-MM-DD"
    receipt_photo: str | None = None
    note: str = ""
    currency: str = "₱"
    created_at: str = ""


@dataclass
class SplitMember:
    """A participant in a split bill."""

    id: str
    name: str  # e.g., "Me", "Alex", "Person 3"
    amount: float = 0.0
    paid: bool = False
    paid_at: str = ""  # ISO "YYYY-MM-DD"


@dataclass
class SplitBill:
    """A shared group bill split among multiple people."""

    id: str
    title: str  # e.g., "Dinner at Samgyup", "Groceries"
    total_amount: float
    split_mode: str = "equal"  # "equal" | "custom"
    members: list[SplitMember] = field(default_factory=list)
    qr_image_path: str | None = None  # User's uploaded digital bank QR
    currency: str = "₱"
    date: str = ""  # ISO "YYYY-MM-DD"
    settled: bool = False
    rewarded: bool = False  # Coins and Steward XP awarded upon 100% settlement
    receipt_photo: str | None = None
    created_at: str = ""

    @property
    def paid_count(self) -> int:
        return sum(1 for m in self.members if m.paid)

    @property
    def total_members(self) -> int:
        return len(self.members)

    @property
    def is_all_paid(self) -> bool:
        return len(self.members) > 0 and all(m.paid for m in self.members)

    @property
    def amount_collected(self) -> float:
        return sum(m.amount for m in self.members if m.paid)

    @property
    def amount_remaining(self) -> float:
        return max(0.0, self.total_amount - self.amount_collected)


def extract_receipt_total(text: str) -> float | None:
    """Smart heuristic to extract total amount from receipt OCR text globally.
    
    Supports global currencies ($, €, £, ¥, ₹, ₩, ₱, USD, EUR, GBP, JPY, INR, KRW, PHP, AUD, CAD, SGD)
    and keywords like TOTAL, AMOUNT DUE, BALANCE, GRAND TOTAL, NET.
    """
    if not text:
        return None

    lines = [line.strip().upper() for line in text.splitlines() if line.strip()]

    # Pattern for numbers like 1,500.00, 1500.50, 1500, 12.99 with optional global currency prefix
    num_pattern = re.compile(
        r"(?:PHP|USD|EUR|GBP|JPY|INR|KRW|AUD|CAD|SGD|A\$|C\$|S\$|[₱$€£¥₹₩])?\s*"
        r"([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)"
    )

    candidates: list[float] = []

    # Priority 1: Lines containing "TOTAL", "AMOUNT DUE", "GRAND TOTAL", "NET", or currency codes
    keywords = (
        "TOTAL",
        "GRAND TOTAL",
        "AMOUNT DUE",
        "BALANCE DUE",
        "NET AMOUNT",
        "PHP",
        "USD",
        "EUR",
        "GBP",
        "AUD",
        "CAD",
        "SGD",
        "₱",
        "$",
        "€",
        "£",
        "¥",
        "₹",
        "₩",
    )
    for line in reversed(lines):  # Total usually appears toward the bottom
        for kw in keywords:
            if kw in line and "SUBTOTAL" not in line and "ITEMS" not in line and "CHANGE" not in line:
                matches = num_pattern.findall(line)
                for m in matches:
                    try:
                        clean = m.replace(",", "").replace(" ", "")
                        val = float(clean)
                        if 1.0 <= val <= 500_000.0:  # Sensible range for consumer receipts
                            candidates.append(val)
                    except ValueError:
                        continue

    if candidates:
        return max(candidates)

    # Priority 2: Fallback to largest currency number found anywhere
    all_matches = num_pattern.findall(text)
    vals = []
    for m in all_matches:
        try:
            val = float(m.replace(",", "").replace(" ", ""))
            if 5.0 <= val <= 250_000.0:
                vals.append(val)
        except ValueError:
            continue

    return max(vals) if vals else None


def calculate_equal_split(total: float, num_people: int) -> list[float]:
    """Split `total` evenly across `num_people`, distributing centavos/cents correctly."""
    if num_people <= 0:
        return []
    base = round(total / num_people, 2)
    shares = [base] * num_people
    diff = round(total - sum(shares), 2)
    if diff != 0:
        shares[0] = round(shares[0] + diff, 2)
    return shares


def create_split_bill(
    bill_id: str,
    title: str,
    total: float,
    num_people: int = 2,
    names: list[str] | None = None,
    qr_image_path: str | None = None,
    custom_amounts: list[float] | None = None,
    receipt_photo: str | None = None,
    today_str: str | None = None,
) -> SplitBill:
    """Helper to initialize a split bill with members."""
    iso_today = today_str or date.today().isoformat()
    count = max(1, num_people)

    if custom_amounts and len(custom_amounts) == count:
        mode = "custom"
        shares = custom_amounts
    else:
        mode = "equal"
        shares = calculate_equal_split(total, count)

    members: list[SplitMember] = []
    for i in range(count):
        if names and i < len(names) and names[i].strip():
            name = names[i].strip()
        else:
            name = "You (Host)" if i == 0 else f"Person {i + 1}"
        members.append(
            SplitMember(
                id=f"m_{i + 1}",
                name=name,
                amount=shares[i],
                paid=(i == 0),  # Host is considered paid by default
                paid_at=iso_today if i == 0 else "",
            )
        )

    return SplitBill(
        id=bill_id,
        title=title.strip() or "Group Split Bill",
        total_amount=round(total, 2),
        split_mode=mode,
        members=members,
        qr_image_path=qr_image_path,
        currency="₱",
        date=iso_today,
        settled=all(m.paid for m in members),
        rewarded=False,
        receipt_photo=receipt_photo,
        created_at=iso_today,
    )


# --- Savings Goals & Projected Interest Vault ------------------------------------

DEFAULT_SAVINGS_APY: float = 4.5


@dataclass
class SavingsGoal:
    """A target savings goal or vault with projected yield/interest."""

    id: str
    name: str
    target_amount: float
    current_amount: float = 0.0
    apy_percent: float = DEFAULT_SAVINGS_APY
    created_at: str = ""  # ISO "YYYY-MM-DD"
    icon: str = "savings"
    notes: str = ""
    rewarded: bool = False

    @property
    def daily_interest(self) -> float:
        return calculate_daily_projected_earnings(self.current_amount, self.apy_percent)

    @property
    def monthly_interest(self) -> float:
        return calculate_monthly_projected_earnings(self.current_amount, self.apy_percent)

    @property
    def progress(self) -> float:
        return calculate_milestone_progress(self.current_amount, self.target_amount)

    @property
    def is_reached(self) -> bool:
        return self.target_amount > 0 and self.current_amount >= self.target_amount

    def deposit(self, amount: float) -> float:
        return deposit_to_savings_goal(self, amount)

    def withdraw(self, amount: float) -> float:
        return withdraw_from_savings_goal(self, amount)


def calculate_daily_projected_earnings(
    current_amount: float, apy_percent: float = DEFAULT_SAVINGS_APY
) -> float:
    """Calculate daily projected interest earnings: current_amount * (apy_percent / 100) / 365."""
    if current_amount <= 0 or apy_percent <= 0:
        return 0.0
    return (current_amount * (apy_percent / 100.0)) / 365.0


def calculate_monthly_projected_earnings(
    current_amount: float, apy_percent: float = DEFAULT_SAVINGS_APY
) -> float:
    """Calculate monthly projected interest earnings: current_amount * (apy_percent / 100) / 12."""
    if current_amount <= 0 or apy_percent <= 0:
        return 0.0
    return (current_amount * (apy_percent / 100.0)) / 12.0


def calculate_milestone_progress(current_amount: float, target_amount: float) -> float:
    """Calculate milestone progress ratio (0.0 to 1.0 or higher if exceeded)."""
    if target_amount <= 0:
        return 1.0 if current_amount > 0 else 0.0
    return max(0.0, current_amount / target_amount)


def deposit_to_savings_goal(goal: SavingsGoal, amount: float) -> float:
    """Deposit an amount into the savings goal. Returns new current_amount."""
    if amount <= 0:
        return goal.current_amount
    goal.current_amount = round(goal.current_amount + amount, 2)
    return goal.current_amount


def withdraw_from_savings_goal(goal: SavingsGoal, amount: float) -> float:
    """Withdraw an amount from the savings goal. Returns actual amount withdrawn."""
    if amount <= 0:
        return 0.0
    actual = min(goal.current_amount, amount)
    goal.current_amount = round(goal.current_amount - actual, 2)
    return actual


def create_savings_goal(
    goal_id: str,
    name: str,
    target_amount: float,
    current_amount: float = 0.0,
    apy_percent: float = DEFAULT_SAVINGS_APY,
    created_at: str | None = None,
    icon: str = "savings",
    notes: str = "",
) -> SavingsGoal:
    """Helper to initialize a new savings goal."""
    return SavingsGoal(
        id=goal_id,
        name=name.strip() or "Savings Goal",
        target_amount=round(max(0.0, target_amount), 2),
        current_amount=round(max(0.0, current_amount), 2),
        apy_percent=float(apy_percent),
        created_at=created_at or date.today().isoformat(),
        icon=icon,
        notes=notes.strip(),
        rewarded=False,
    )
