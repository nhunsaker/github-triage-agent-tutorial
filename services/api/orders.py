"""Order placement and checkout for Jane's Jeans."""
import itertools

from services.api import events, inventory


class OrderValidationError(Exception):
    """Raised when an incoming order fails basic validation."""


class CheckoutError(Exception):
    """Raised when checkout fails for a reason other than validation or stock."""


ORDERS = {}
_order_ids = itertools.count(1)


def validate_order(payload):
    if not payload.get("sku"):
        raise OrderValidationError("order rejected: missing sku")
    if not payload.get("quantity") or payload["quantity"] <= 0:
        raise OrderValidationError("order rejected: quantity must be positive")


def place_order(payload):
    validate_order(payload)
    sku = payload["sku"]
    quantity = payload["quantity"]
    cart_id = payload.get("cart_id", f"cart-{sku}")

    try:
        inventory.reserve(sku, quantity)
    except inventory.OversellError:
        raise
    except KeyError as e:
        # unknown sku slipping past validation is an internal bug, not a bad request
        raise CheckoutError(
            f"checkout failed for cart {cart_id}: internal error"
        ) from e

    order_id = next(_order_ids)
    order = {"id": order_id, "sku": sku, "quantity": quantity, "status": "placed"}
    ORDERS[order_id] = order
    events.publish("orders", {"type": "order_placed", "order": order})
    return order
