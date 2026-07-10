from datetime import timedelta

from app.models.schemas import Signals, Transaction

STRUCTURING_BAND_LOW = 9500.0
STRUCTURING_BAND_HIGH = 9999.99
DUPLICATE_WINDOW_DAYS = 5
DUPLICATE_AMOUNT_TOLERANCE = 0.01
BUSINESS_HOURS_START = 8
BUSINESS_HOURS_END = 18


def compute_signals(transaction: Transaction, all_transactions: list[Transaction]) -> Signals:
    duplicate_candidate_ids = [
        other.transaction_id
        for other in all_transactions
        if other.transaction_id != transaction.transaction_id
        and other.vendor == transaction.vendor
        and abs(other.amount - transaction.amount) <= transaction.amount * DUPLICATE_AMOUNT_TOLERANCE
        and abs((other.date - transaction.date)) <= timedelta(days=DUPLICATE_WINDOW_DAYS)
    ]

    in_structuring_band = STRUCTURING_BAND_LOW <= transaction.amount <= STRUCTURING_BAND_HIGH

    is_off_hours = (
        transaction.date.weekday() >= 5
        or not (BUSINESS_HOURS_START <= transaction.date.hour < BUSINESS_HOURS_END)
    )

    return Signals(
        duplicate_candidate_ids=duplicate_candidate_ids,
        in_structuring_band=in_structuring_band,
        is_off_hours=is_off_hours,
    )
