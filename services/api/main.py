"""Jane's Jeans API: orders, inventory, returns. Run with:
    uvicorn services.api.main:app --reload
"""
from fastapi import FastAPI, HTTPException

from services.api import inventory, orders, returns

app = FastAPI(title="Jane's Jeans API")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/orders")
def create_order(payload: dict):
    try:
        return orders.place_order(payload)
    except orders.OrderValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except inventory.OversellError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except orders.CheckoutError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stock/{sku}")
def get_stock(sku: str):
    try:
        return {"sku": sku, "on_hand": inventory.get_stock(sku)}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown sku {sku}")


@app.post("/returns")
def create_return(payload: dict):
    """Body {"order_id": ...} starts a return; {"return_id": ..., "action": ...} advances one."""
    if "action" in payload:
        try:
            return returns.advance(payload["return_id"], payload["action"])
        except returns.ReturnStateError as e:
            raise HTTPException(status_code=409, detail=str(e))
    return returns.start_return(payload.get("order_id"))
