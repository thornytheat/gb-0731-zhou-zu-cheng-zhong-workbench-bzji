from typing import Any

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from app.modules.m8_upgrades.service import assess_upgrade

router = APIRouter(prefix="/api/upgrades", tags=["升级复核"])


class UpgradeInput(BaseModel):
    run_id: str
    rules: str
    parameters: dict[str, Any] = Field(default_factory=dict)


def _summary(order):
    return {
        "order_id": order["order_id"],
        "created_at": order["created_at"],
        "run_id": order["run_id"],
        "sample": order["sample"],
        "from_rules": order["from"]["rules"],
        "to_rules": order["to"]["rules"],
        "parameter_changes": len(order["parameter_changes"]),
        "summary": order["summary"],
    }


@router.get("")
def list_upgrades(request: Request):
    return {"orders": [_summary(order) for order in request.app.state.store.order_history()]}


@router.post("", status_code=201)
def create_upgrade(payload: UpgradeInput, request: Request, response: Response):
    order, reused = assess_upgrade(
        request.app.state.store, request.app.state.settings.source_dir,
        payload.run_id, payload.rules, payload.parameters,
    )
    if reused:
        response.status_code = 200
    return {"order": order, "reused": reused}


@router.get("/{order_id}")
def show_upgrade(order_id: str, request: Request):
    return {"order": request.app.state.store.read_order(order_id)}
