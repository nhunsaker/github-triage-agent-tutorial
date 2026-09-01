"""Stock tracking for Jane's Jeans."""


class OversellError(Exception):
    """Raised when reserving stock would push on-hand quantity below zero."""


# seed inventory: sku -> on-hand quantity. JJ-720-28 is seeded at 0 on purpose
# (it's the sku the oversell tests/demo issues hit).
STOCK = {
    "JJ-501-32": 12,
    "JJ-501-34": 8,
    "JJ-720-28": 0,
    "JJ-999-30": 25,
}


def get_stock(sku):
    """Raises KeyError for an unknown sku."""
    return STOCK[sku]


def reserve(sku, quantity):
    """Reserve `quantity` units of `sku`, decrementing on-hand stock.

    Raises KeyError for an unknown sku, OversellError if the reservation
    would take on-hand stock below zero.
    """
    on_hand = STOCK[sku]
    if on_hand - quantity < 0:
        raise OversellError(
            f"stock below zero for sku {sku}: reserved {quantity}, on hand {on_hand}"
        )
    STOCK[sku] = on_hand - quantity
    return STOCK[sku]
