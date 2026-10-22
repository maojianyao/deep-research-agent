"""HTTP endpoints for persistent, completed-report follow-up threads."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request, status

from backend.src.research.schemas import RunStatus
from backend.src.services.follow_up import (
    normalize_report_text, report_anchor_digest,
)

from .follow_up_schemas import (
    CreateFollowUpThread, FollowUpThreadList, FollowUpThreadView,
)


router = APIRouter(
    prefix="/api/research-runs/{run_id}/follow-ups",
    tags=["follow-ups"],
)


def _eligible_run(repository, run_id: str):
    run = repository.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    if run.status != RunStatus.COMPLETED.value:
        raise HTTPException(status_code=409, detail="Research run is not completed")
    if run.report is None:
        raise HTTPException(status_code=409, detail="Research report is not ready")
    return run


def _validate_anchor(anchor, report_markdown: str):
    if anchor.end - anchor.start != len(anchor.text):
        raise HTTPException(status_code=422, detail="Selection offsets do not match the selected text")
    if anchor.report_digest != report_anchor_digest(report_markdown):
        raise HTTPException(status_code=422, detail="Report digest is stale or invalid")
    report_text = normalize_report_text(report_markdown)
    if anchor.end > len(report_text) or report_text[anchor.start:anchor.end] != anchor.text:
        raise HTTPException(status_code=422, detail="Selection is outside the report body")


@router.get("", response_model=FollowUpThreadList)
def list_follow_ups(run_id: str, request: Request):
    _eligible_run(request.app.state.repository, run_id)
    return {"items": request.app.state.follow_up_repository.list_threads(run_id)}


@router.post("", response_model=FollowUpThreadView, status_code=status.HTTP_201_CREATED)
async def create_follow_up(run_id: str, payload: CreateFollowUpThread, request: Request):
    run = _eligible_run(request.app.state.repository, run_id)
    _validate_anchor(payload.anchor, run.report.markdown)
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Question cannot be blank")

    history = [{"role": "user", "content": question}]
    answerer = request.app.state.follow_up_answerer
    try:
        answer = await answerer.answer(payload.anchor.text, history)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Follow-up answer generation failed") from exc
    if not answer.strip():
        raise HTTPException(status_code=502, detail="Follow-up answer was empty")

    return await asyncio.to_thread(
        request.app.state.follow_up_repository.create_thread,
        run_id=run_id,
        anchor=payload.anchor.model_dump(),
        question=question,
        answer=answer.strip(),
    )
