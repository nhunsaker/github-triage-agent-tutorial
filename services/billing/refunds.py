"""Refund orchestration for Jane's Jeans returns."""
from services.billing import payflow


class RefundDeclinedError(Exception):
    """Raised when the vendor declines a refund."""


def refund_order(order_id, mode=None):
    result = payflow.refund(order_id, mode=mode)
    if result.get("status") == "declined":
        raise RefundDeclinedError(
            f"refund declined by vendor for order {order_id}: code {result['code']}"
        )
    return result
