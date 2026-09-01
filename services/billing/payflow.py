"""Thin client for the fictional PayFlow vendor (wraps vendor_stub)."""
from services.billing import vendor_stub


class PayFlowUnavailableError(Exception):
    """Raised when PayFlow is unreachable (vendor outage)."""


class PayFlowDeprecationError(Exception):
    """Raised when calling a PayFlow v1 endpoint after the vendor's v2 cutover."""


def _call(fn, *args, mode=None):
    try:
        return fn(*args, mode=mode)
    except vendor_stub.VendorOutageError as e:
        raise PayFlowUnavailableError(str(e)) from e
    except vendor_stub.DeprecatedEndpointError as e:
        raise PayFlowDeprecationError(
            f"PayFlow v1 endpoint '{e.endpoint}' is deprecated, migrate to v2"
        ) from e


def charge(order_id, amount, mode=None):
    return _call(vendor_stub.charge, order_id, amount, mode=mode)


def refund(order_id, mode=None):
    return _call(vendor_stub.refund, order_id, mode=mode)
