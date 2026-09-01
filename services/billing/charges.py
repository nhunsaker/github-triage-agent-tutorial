"""Charge orchestration for Jane's Jeans checkout."""
from services.billing import payflow


class DuplicateChargeError(Exception):
    """Raised when a charge is attempted twice for the same order."""


_charged_orders = set()


def charge_order(order_id, amount, mode=None):
    if order_id in _charged_orders:
        raise DuplicateChargeError(f"duplicate charge attempt blocked for order {order_id}")
    result = payflow.charge(order_id, amount, mode=mode)
    _charged_orders.add(order_id)
    return result
