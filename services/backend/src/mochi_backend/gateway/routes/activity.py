"""Describe & Guess endpoints. The Home view sends the result (second tap or long press)."""

from fastapi import APIRouter
from pydantic import BaseModel

from mochi_backend.gateway.routes.dependencies import ContainerDep
from mochi_contracts import Activity, RoundResult

router = APIRouter()


class ResultBody(BaseModel):
    """`{"result": "guessed" | "skipped"}`."""

    result: RoundResult


@router.post("/api/sessions/demo/activity/start")
async def start_activity(container: ContainerDep) -> Activity:
    """Start a round."""
    return await container.activity.start()


@router.post("/api/sessions/demo/activity/result")
async def finish_activity(body: ResultBody, container: ContainerDep) -> Activity:
    """Record how the round ended."""
    return await container.activity.finish(body.result)
