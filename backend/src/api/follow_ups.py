"""HTTP and SSE endpoints for durable report follow-up generation."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from backend.src.research.schemas import RunStatus
from backend.src.services.follow_up import (
    bounded_follow_up_history, normalize_report_text, report_anchor_digest,
)
from backend.src.storage import (
    FollowUpBusyError, FollowUpNotFoundError, FollowUpNotRetryableError,
    FollowUpOverlapError,
)

from .follow_up_schemas import (
    AppendFollowUpQuestion, CreateFollowUpThread, FollowUpThreadList,
    FollowUpThreadView, UpdateFollowUpState,
)


router = APIRouter(
    prefix="/api/research-runs/{run_id}/follow-ups",
    tags=["follow-ups"],
)
TERMINAL_EVENTS = {"completed", "failed", "interrupted"}


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

    lock = request.app.state.follow_up_locks.setdefault(f"run:{run_id}", asyncio.Lock())
    async with lock:
        try:
            started = await asyncio.to_thread(
                request.app.state.follow_up_repository.start_thread,
                run_id=run_id,
                anchor=payload.anchor.model_dump(),
                question=question,
            )
        except FollowUpOverlapError as exc:
            raise HTTPException(
                status_code=409,
                detail="Selection overlaps an existing follow-up conversation",
            ) from exc
    _start_generation(request, started)
    return started.thread


@router.get("/{thread_id}", response_model=FollowUpThreadView)
def get_follow_up(run_id: str, thread_id: str, request: Request):
    _eligible_run(request.app.state.repository, run_id)
    thread = request.app.state.follow_up_repository.get_thread(run_id, thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Follow-up thread not found")
    return thread


@router.delete("/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_follow_up(run_id: str, thread_id: str, request: Request):
    _eligible_run(request.app.state.repository, run_id)
    lock = request.app.state.follow_up_locks.setdefault(thread_id, asyncio.Lock())
    async with lock:
        await cancel_follow_up_tasks(request, [thread_id])
        deleted = await asyncio.to_thread(
            request.app.state.follow_up_repository.delete_thread,
            run_id,
            thread_id,
        )
        request.app.state.follow_up_locks.pop(thread_id, None)
    if not deleted:
        raise HTTPException(status_code=404, detail="Follow-up thread not found")


@router.post("/{thread_id}/questions", response_model=FollowUpThreadView,
             status_code=status.HTTP_201_CREATED)
async def append_follow_up_question(
    run_id: str, thread_id: str, payload: AppendFollowUpQuestion, request: Request,
):
    _eligible_run(request.app.state.repository, run_id)
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Question cannot be blank")
    lock = request.app.state.follow_up_locks.setdefault(thread_id, asyncio.Lock())
    async with lock:
        try:
            started = await asyncio.to_thread(
                request.app.state.follow_up_repository.append_question,
                run_id=run_id,
                thread_id=thread_id,
                question=question,
            )
        except FollowUpBusyError as exc:
            raise HTTPException(status_code=409, detail="Follow-up answer is still generating") from exc
        except FollowUpNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Follow-up thread not found") from exc
        _start_generation(request, started)
        return started.thread


@router.post("/{thread_id}/messages/{message_id}/retry",
             response_model=FollowUpThreadView, status_code=status.HTTP_202_ACCEPTED)
async def retry_follow_up_message(
    run_id: str, thread_id: str, message_id: int, request: Request,
):
    _eligible_run(request.app.state.repository, run_id)
    lock = request.app.state.follow_up_locks.setdefault(thread_id, asyncio.Lock())
    async with lock:
        try:
            started = await asyncio.to_thread(
                request.app.state.follow_up_repository.retry_message,
                run_id=run_id,
                thread_id=thread_id,
                message_id=message_id,
            )
        except FollowUpBusyError as exc:
            raise HTTPException(status_code=409, detail="Follow-up answer is still generating") from exc
        except FollowUpNotRetryableError as exc:
            raise HTTPException(status_code=409, detail="Follow-up answer cannot be retried") from exc
        except FollowUpNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Follow-up message not found") from exc
        _start_generation(request, started)
        return started.thread


@router.post("/{thread_id}/state", response_model=FollowUpThreadList)
def update_follow_up_state(
    run_id: str, thread_id: str, payload: UpdateFollowUpState, request: Request,
):
    _eligible_run(request.app.state.repository, run_id)
    items = request.app.state.follow_up_repository.set_minimized(
        run_id, thread_id, payload.minimized
    )
    if items is None:
        raise HTTPException(status_code=404, detail="Follow-up thread not found")
    return {"items": items}


@router.get("/{thread_id}/events")
async def stream_follow_up_events(
    run_id: str,
    thread_id: str,
    request: Request,
    after_sequence: int = Query(default=0, ge=0),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
):
    _eligible_run(request.app.state.repository, run_id)
    repository = request.app.state.follow_up_repository
    if repository.get_thread(run_id, thread_id) is None:
        raise HTTPException(status_code=404, detail="Follow-up thread not found")
    if last_event_id and last_event_id.isdigit():
        after_sequence = max(after_sequence, int(last_event_id))

    async def events() -> AsyncIterator[str]:
        cursor = after_sequence
        last_heartbeat = asyncio.get_running_loop().time()
        while not await request.is_disconnected():
            items = await asyncio.to_thread(
                repository.list_events_after, thread_id, cursor
            )
            for item in items:
                cursor = item["sequence"]
                payload = json.dumps(item, ensure_ascii=False, default=str)
                yield f"id: {cursor}\nevent: follow-up\ndata: {payload}\n\n"
                if item["type"] in TERMINAL_EVENTS:
                    return
            if not items and not await asyncio.to_thread(
                repository.has_generating_message, thread_id
            ):
                return
            now = asyncio.get_running_loop().time()
            if now - last_heartbeat >= 15:
                yield ": keep-alive\n\n"
                last_heartbeat = now
            await asyncio.sleep(0.05)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


def _start_generation(request: Request, started) -> None:
    tasks: dict[str, asyncio.Task] = request.app.state.follow_up_tasks
    thread_id = started.thread["id"]

    async def generate() -> None:
        repository = request.app.state.follow_up_repository
        answerer = request.app.state.follow_up_answerer
        received = False
        try:
            async for chunk in _stream_chunks(answerer, started):
                if not chunk:
                    continue
                received = True
                await asyncio.to_thread(
                    repository.append_delta,
                    thread_id,
                    started.assistant_message_id,
                    chunk,
                )
            if received:
                await asyncio.to_thread(
                    repository.complete_message,
                    thread_id,
                    started.assistant_message_id,
                )
            else:
                await asyncio.to_thread(
                    repository.fail_message,
                    thread_id,
                    started.assistant_message_id,
                    "Follow-up answer was empty",
                )
        except asyncio.CancelledError:
            await asyncio.to_thread(
                repository.interrupt_message,
                thread_id,
                started.assistant_message_id,
            )
            raise
        except Exception as exc:
            await asyncio.to_thread(
                repository.fail_message,
                thread_id,
                started.assistant_message_id,
                str(exc)[:500] or "Follow-up answer generation failed",
            )

    previous = tasks.get(thread_id)

    async def generate_after_previous() -> None:
        await asyncio.gather(previous, return_exceptions=True)
        await generate()

    coroutine = (
        generate_after_previous()
        if previous is not None and not previous.done()
        else generate()
    )
    task = asyncio.create_task(coroutine, name=f"follow-up-{thread_id}")
    tasks[thread_id] = task

    def remove_finished(completed: asyncio.Task) -> None:
        if tasks.get(thread_id) is completed:
            tasks.pop(thread_id, None)

    task.add_done_callback(remove_finished)


async def cancel_follow_up_tasks(request: Request, thread_ids: list[str]) -> None:
    tasks: dict[str, asyncio.Task] = request.app.state.follow_up_tasks
    cancelled = []
    for thread_id in thread_ids:
        task = tasks.get(thread_id)
        if task is not None and not task.done():
            task.cancel()
            cancelled.append(task)
    if cancelled:
        await asyncio.gather(*cancelled, return_exceptions=True)
    for thread_id in thread_ids:
        tasks.pop(thread_id, None)


async def _stream_chunks(answerer, started) -> AsyncIterator[str]:
    passage = started.thread["anchor"]["text"]
    history = bounded_follow_up_history(passage, started.history)
    if hasattr(answerer, "stream"):
        async for chunk in answerer.stream(passage, history):
            yield chunk
        return
    yield await answerer.answer(passage, history)
