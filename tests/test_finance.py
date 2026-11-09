"""Unit tests for Receipt Scanning, Split Bills, and Expense Tracking (Finance Hub)."""

from datetime import date
from pathlib import Path

import pytest

from lol.core.finance import (
    DEFAULT_SAVINGS_APY,
    calculate_daily_projected_earnings,
    calculate_equal_split,
    calculate_monthly_projected_earnings,
    create_savings_goal,
    create_split_bill,
    extract_receipt_total,
)
from lol.core.models import SaveData
from lol.core.storage import from_dict, to_dict


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path))


def test_extract_receipt_total_standard_ph_receipt():
    sample_ocr = """
    SAMGYUPSAL HOUSE RESTAURANT
    123 AYALA AVE, MAKATI CITY
    TIN: 123-456-789-000
    
    1 PORK BELLY SET     500.00
    2 BEEF SHORT PLATE   800.00
    1 ICED TEA PITCHER   200.00
    
    SUBTOTAL           1,500.00
    VAT 12%              180.00
    SERVICE CHARGE        50.00
    TOTAL AMOUNT DUE   1,730.00
    CASH               2,000.00
    CHANGE               270.00
    
    THANK YOU PLEASE COME AGAIN!
    """
    total = extract_receipt_total(sample_ocr)
    assert total == 1730.0


def test_extract_receipt_total_global_currencies():
    us_receipt = "SUBTOTAL $42.00\nTAX $3.50\nTOTAL $45.50"
    assert extract_receipt_total(us_receipt) == 45.50

    eu_receipt = "Subtotal €18.00\nGrand Total €21.80"
    assert extract_receipt_total(eu_receipt) == 21.80

    uk_receipt = "Amount Due £64.25"
    assert extract_receipt_total(uk_receipt) == 64.25


def test_calculate_equal_split():
    # ₱1,500 among 4 people = 375 each
    shares = calculate_equal_split(1500.0, 4)
    assert len(shares) == 4
    assert sum(shares) == 1500.0
    assert shares == [375.0, 375.0, 375.0, 375.0]

    # Odd division: ₱100 among 3 people = 33.34, 33.33, 33.33
    shares_odd = calculate_equal_split(100.0, 3)
    assert len(shares_odd) == 3
    assert sum(shares_odd) == 100.0
    assert shares_odd[0] == 33.34
    assert shares_odd[1] == 33.33
    assert shares_odd[2] == 33.33


def test_create_split_bill_and_status():
    bill = create_split_bill(
        bill_id="sb_1",
        title="Samgyup Dinner",
        total=1500.0,
        num_people=4,
        names=["Me", "Alex", "Jordan", "Sam"],
    )
    assert bill.total_amount == 1500.0
    assert len(bill.members) == 4
    assert bill.members[0].name == "Me"
    assert bill.members[0].paid is True  # Host starts marked as paid
    assert bill.members[1].paid is False
    assert bill.amount_collected == 375.0
    assert bill.amount_remaining == 1125.0
    assert not bill.is_all_paid

    # Mark all members as paid
    for m in bill.members:
        m.paid = True
    assert bill.is_all_paid
    assert bill.amount_remaining == 0.0


def test_split_bill_persistence():
    bill = create_split_bill(
        bill_id="sb_10",
        title="Lunch",
        total=600.0,
        num_people=3,
    )
    save_data = SaveData()
    save_data.split_bills = [bill]
    save_data.saved_qr_path = "qr_codes/gcash_my_qr.png"

    raw = to_dict(save_data)
    loaded = from_dict(raw, date.today())

    assert len(loaded.split_bills) == 1
    loaded_bill = loaded.split_bills[0]
    assert loaded_bill.title == "Lunch"
    assert loaded_bill.total_amount == 600.0
    assert len(loaded_bill.members) == 3
    assert loaded.saved_qr_path == "qr_codes/gcash_my_qr.png"


def test_savings_goal_calculations_and_persistence():
    # ₱100,000 at 4.5% APY
    # Daily interest = 100,000 * 0.045 / 365 = ~12.3287
    daily = calculate_daily_projected_earnings(100000.0, 4.5)
    assert round(daily, 2) == 12.33

    monthly = calculate_monthly_projected_earnings(100000.0, 4.5)
    assert round(monthly, 2) == 375.00

    goal = create_savings_goal(
        goal_id="sg_1",
        name="Emergency Vault",
        target_amount=100000.0,
        current_amount=25000.0,
        apy_percent=DEFAULT_SAVINGS_APY,
        notes="6-month buffer",
    )
    assert goal.progress == 0.25
    assert not goal.is_reached

    # Deposit
    goal.deposit(75000.0)
    assert goal.current_amount == 100000.0
    assert goal.is_reached

    # Withdraw
    w = goal.withdraw(10000.0)
    assert w == 10000.0
    assert goal.current_amount == 90000.0

    # Persistence
    save_data = SaveData()
    save_data.savings_goals = [goal]
    raw = to_dict(save_data)
    loaded = from_dict(raw, date.today())
    assert len(loaded.savings_goals) == 1
    lg = loaded.savings_goals[0]
    assert lg.name == "Emergency Vault"
    assert lg.current_amount == 90000.0
    assert lg.target_amount == 100000.0
    assert lg.apy_percent == DEFAULT_SAVINGS_APY

