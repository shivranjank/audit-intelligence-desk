from datetime import datetime

from app.models.schemas import Transaction
from app.services.signals import compute_signals


def _txn(transaction_id: str, vendor: str, amount: float, date: str, description: str = "") -> Transaction:
    return Transaction(
        transaction_id=transaction_id,
        date=datetime.fromisoformat(date),
        vendor=vendor,
        amount=amount,
        department="Finance",
        account_code="6010-TRAVEL",
        approver="A. Test",
        description=description,
    )


def test_duplicate_candidates_same_vendor_amount_within_window() -> None:
    a = _txn("TXN-A", "Acme Co", 1000.0, "2026-06-11T12:00:00")
    b = _txn("TXN-B", "Acme Co", 1000.0, "2026-06-12T12:00:00")
    signals = compute_signals(a, [a, b])
    assert signals.duplicate_candidate_ids == ["TXN-B"]


def test_no_duplicate_when_amount_differs_beyond_tolerance() -> None:
    a = _txn("TXN-A", "Acme Co", 1000.0, "2026-06-11T12:00:00")
    b = _txn("TXN-B", "Acme Co", 1200.0, "2026-06-12T12:00:00")
    signals = compute_signals(a, [a, b])
    assert signals.duplicate_candidate_ids == []


def test_no_duplicate_when_outside_window() -> None:
    a = _txn("TXN-A", "Acme Co", 1000.0, "2026-06-01T12:00:00")
    b = _txn("TXN-B", "Acme Co", 1000.0, "2026-06-20T12:00:00")
    signals = compute_signals(a, [a, b])
    assert signals.duplicate_candidate_ids == []


def test_structuring_band() -> None:
    in_band = _txn("TXN-A", "Acme Co", 9800.0, "2026-06-11T12:00:00")
    below_band = _txn("TXN-B", "Acme Co", 9000.0, "2026-06-11T12:00:00")
    assert compute_signals(in_band, [in_band]).in_structuring_band is True
    assert compute_signals(below_band, [below_band]).in_structuring_band is False


def test_off_hours_weekday_evening() -> None:
    off_hours = _txn("TXN-A", "Acme Co", 100.0, "2026-06-11T23:00:00")  # Thursday 11pm
    business_hours = _txn("TXN-B", "Acme Co", 100.0, "2026-06-11T12:00:00")  # Thursday noon
    assert compute_signals(off_hours, [off_hours]).is_off_hours is True
    assert compute_signals(business_hours, [business_hours]).is_off_hours is False


def test_off_hours_weekend() -> None:
    weekend = _txn("TXN-A", "Acme Co", 100.0, "2026-06-13T12:00:00")  # Saturday
    assert compute_signals(weekend, [weekend]).is_off_hours is True
