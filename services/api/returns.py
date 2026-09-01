"""Returns processing for Jane's Jeans."""

class ReturnStateError(Exception):
    """Raised when a return action isn't valid for the return's current state."""


RETURNS = {}


def _id_counter():
    n = 1
    while True:
        yield n
        n += 1


_ids = _id_counter()

VALID_ACTIONS = {
    "requested": {"approve", "reject"},
    "approved": {"refund"},
    "rejected": set(),
    "refunded": set(),
}

NEXT_STATE = {"approve": "approved", "reject": "rejected", "refund": "refunded"}


def start_return(order_id):
    return_id = next(_ids)
    RETURNS[return_id] = {"id": return_id, "order_id": order_id, "state": "requested"}
    return RETURNS[return_id]


def advance(return_id, action):
    ret = RETURNS[return_id]
    state = ret["state"]
    if action not in VALID_ACTIONS.get(state, set()):
        raise ReturnStateError(
            f"return {return_id} is in state '{state}', cannot {action}"
        )
    ret["state"] = NEXT_STATE[action]
    return ret
