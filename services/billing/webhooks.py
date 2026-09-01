"""PayFlow webhook verification for Jane's Jeans."""
from services.billing import vendor_stub


class WebhookVerificationError(Exception):
    """Raised when a PayFlow webhook's signature doesn't verify."""


def handle_webhook(payload, signature, delivery_id, mode=None):
    if not vendor_stub.verify_webhook_signature(payload, signature, mode=mode):
        raise WebhookVerificationError(
            f"webhook signature verification failed for delivery {delivery_id}"
        )
    return {"status": "ok"}
