"""A local fake of the fictional PayFlow vendor. Scriptable failures, no network.

Mode comes from the `mode` arg, else the PAYFLOW_MODE env var, else "normal".
Modes:
  normal      - everything succeeds
  outage      - raises VendorOutageError (a 503) on every call
  declined    - charges/refunds come back declined
  v2_cutover  - v1 endpoints raise DeprecatedEndpointError
  bad_signature - webhook signatures fail to verify
"""
import os


class VendorOutageError(Exception):
    """The vendor is down. Not a catalog symbol itself; billing/*.py wrap this."""


class DeprecatedEndpointError(Exception):
    """A v1 endpoint was called after PayFlow's v2 cutover."""

    def __init__(self, endpoint):
        self.endpoint = endpoint
        super().__init__(f"v1 endpoint '{endpoint}' is deprecated")


def _mode(override=None):
    return override or os.environ.get("PAYFLOW_MODE", "normal")


def charge(order_id, amount, mode=None):
    m = _mode(mode)
    if m == "outage":
        raise VendorOutageError("PayFlow API unreachable: 503 from /v1/charges")
    if m == "v2_cutover":
        raise DeprecatedEndpointError("/v1/charges")
    if m == "declined":
        return {"status": "declined", "code": "insufficient_funds"}
    return {"status": "approved", "order_id": order_id, "amount": amount}


def refund(order_id, mode=None):
    m = _mode(mode)
    if m == "outage":
        raise VendorOutageError("PayFlow API unreachable: 503 from /v1/refunds")
    if m == "v2_cutover":
        raise DeprecatedEndpointError("/v1/refunds")
    if m == "declined":
        return {"status": "declined", "code": "policy_declined"}
    return {"status": "refunded", "order_id": order_id}


def verify_webhook_signature(payload, signature, mode=None):
    m = _mode(mode)
    if m == "bad_signature":
        return False
    return signature == "valid-signature"
