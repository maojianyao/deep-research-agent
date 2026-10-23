"""REST endpoints for creating and browsing long-running research jobs."""

from __future__ import annotations

import asyncio
import inspect
import json
import re

from collections.abc import AsyncIterator

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import PlainTextResponse
from fastapi.responses import StreamingResponse

from backend.src.research.schemas import ResearchRun, RunStatus
from backend.src.research.language import language_profile, resolve_report_language
from backend.src.api.follow_ups import cancel_follow_up_tasks
from backend.src.services.follow_up import report_anchor_digest
from backend.src.storage.repository import ACTIVE_RESEARCH_STATUSES, ResearchRunRepository
from backend.src.utils.logger import get_logger
from .schemas import (
    AcceptedResearchRun, CitationReferenceView, CreateResearchRun, ResearchProgress,
    ReportLanguagePreview, ResearchRunDetail, ResearchRunList, PreviewReportLanguage,
)


router = APIRouter(prefix="/api/research-runs", tags=["research"])
logger = get_logger(__name__)
FINAL_STATUSES = {
    RunStatus.COMPLETED.value,
    RunStatus.NEEDS_HUMAN_REVIEW.value,
    RunStatus.CANCELLED.value,
}
SSE_CLOSED_STATUSES = FINAL_STATUSES | {RunStatus.FAILED.value, RunStatus.PAUSED.value}


def _public_error(exc: Exception) -> str:
    """Keep useful exception details in run history without exposing credentials."""
    message = str(exc).strip() or "未提供异常详情"
    message = re.sub(r"(?i)\bBearer\s+\S+", "Bearer [已隐藏]", message)
    message = re.sub(
        r"(?i)(api[_-]?key|authorization|access[_-]?token|secret)(\s*[:=]\s*)[^\s,;&]+",
        r"\1\2[已隐藏]",
        message,
    )
    message = re.sub(r"\b(?:sk|rk|pk)-[A-Za-z0-9_-]{12,}\b", "[已隐藏密钥]", message)
    return f"{type(exc).__name__}: {message[:500]}"


def _source(source) -> dict:
    return {
        "url": source.url,
        "title": source.title,
        "publisher": source.publisher,
        "published_at": source.published_at,
        "source_type": source.source_type,
    }


def _can_resume(model) -> bool:
    if model.status == RunStatus.COMPLETED.value:
        return False
    if model.status == RunStatus.CANCELLED.value and any(
        event.message == "研究任务已结束" for event in model.events
    ):
        return False
    if model.resume_status:
        return True
    if model.status == RunStatus.PAUSED.value:
        return True
    if model.status == RunStatus.FAILED.value and model.plan is None:
        return True
    if model.plan is None:
        return False
    critique = max(model.critiques, key=lambda item: item.iteration, default=None)
    if critique is not None and critique.iteration == model.iteration:
        return critique.decision != "needs_human_review"
    return model.status in {
        RunStatus.FAILED.value, RunStatus.CANCELLED.value,
        RunStatus.NEEDS_HUMAN_REVIEW.value,
    } and any(
        not task.completed for task in model.tasks
    )


def _restore_checkpoint(run: ResearchRun) -> None:
    if run.resume_status is not None:
        run.status = run.resume_status
        run.iteration = run.resume_iteration
        return
    if run.plan is None:
        run.status = RunStatus.PLANNING
        return
    if run.critique is not None and run.critique.iteration == run.iteration:
        if run.critique.decision == "needs_human_review":
            raise HTTPException(status_code=409, detail="Research run requires human review")
        run.status = (RunStatus.WRITING
                      if run.critique.decision == "approve" or run.iteration >= run.max_iterations
                      else RunStatus.PLANNING)
        return
    critique = max(run.critiques, key=lambda item: item.iteration, default=None)
    if critique is not None and critique.iteration == run.iteration:
        run.critique = critique
        if critique.decision == "needs_human_review":
            raise HTTPException(status_code=409, detail="Research run requires human review")
        run.status = (RunStatus.WRITING
                      if critique.decision == "approve" or run.iteration >= run.max_iterations
                      else RunStatus.PLANNING)
        return
    if f"完成第 {run.iteration} 轮检索" in run.events or all(
        task.completed for task in run.plan.tasks
    ):
        run.status = RunStatus.CRITIC_REVIEW
    else:
        run.iteration = max(0, run.iteration - 1)
        run.status = RunStatus.RESEARCHING


def _detail(model) -> dict:
    critiques = sorted(model.critiques, key=lambda item: item.iteration)
    profile = language_profile(model.report_language)
    return {
        "id": model.id,
        "user_request": model.user_request,
        "report_language": profile.tag,
        "report_language_name": profile.name,
        "report_language_source": model.report_language_source,
        "report_language_quality": profile.quality,
        "report_direction": profile.direction,
        "status": model.status,
        "can_resume": _can_resume(model),
        "error": next((
            event.message.removeprefix("研究执行失败：").split("；详细堆栈已记录", 1)[0]
            for event in reversed(sorted(model.events, key=lambda item: item.sequence))
            if event.message.startswith("研究执行失败：")
        ), None),
        "iteration": model.iteration,
        "max_iterations": model.max_iterations,
        "created_at": model.created_at,
        "updated_at": model.updated_at,
        "plan": None if model.plan is None else {
            "research_question": model.plan.research_question,
            "scope": model.plan.scope,
            "research_domains": model.plan.research_domains or [],
            "risk_level": model.plan.risk_level or "standard",
            "completion_rules": model.plan.completion_rules,
            "tasks": [{
                "id": task.id,
                "question": task.question,
                "task_type": task.task_type,
                "priority": task.priority,
                "required_source_types": task.required_source_types,
                "acceptance_criteria": task.acceptance_criteria,
                "queries": task.queries,
                "attempts": task.attempts,
                "completed": task.completed,
            } for task in model.tasks],
        },
        "candidates": [{
            "task_id": item.task_id,
            "iteration": item.iteration,
            "claim": item.claim,
            "excerpt": item.excerpt,
            "locator": item.locator,
            "source": _source(item.source),
        } for item in model.candidates],
        "evidence": [{
            "id": item.id,
            "task_id": item.task_id,
            "iteration": item.iteration,
            "claim": item.claim,
            "excerpt": item.excerpt,
            "locator": item.locator,
            "verdict": item.verdict,
            "confidence": item.confidence,
            "limitations": item.limitations,
            "source": _source(item.source),
        } for item in model.evidence],
        "findings": [{
            "id": item.id,
            "task_id": item.task_id,
            "iteration": item.iteration,
            "statement": item.statement,
            "classification": item.classification,
            "confidence": item.confidence,
            "caveats": item.caveats,
            "evidence_ids": [evidence.id for evidence in item.evidence],
        } for item in model.findings],
        "critiques": [{
            "iteration": review.iteration,
            "decision": review.decision,
            "approved_finding_ids": [item.id for item in review.approved_findings],
            "issues": [{
                "severity": issue.severity,
                "finding_id": issue.finding_id,
                "problem": issue.problem,
                "follow_up_question": issue.follow_up_question,
                "follow_up_queries": issue.follow_up_queries,
            } for issue in review.issues],
        } for review in critiques],
        "report": None if model.report is None else {
            "title": model.report.title,
            "language": profile.tag,
            "language_name": profile.name,
            "direction": profile.direction,
            "markdown": model.report.markdown,
            "anchor_digest": report_anchor_digest(model.report.markdown),
            "blocks": [{
                "heading": block.heading,
                "text": block.text,
                "finding_ids": [item.id for item in block.findings],
                "evidence_ids": [item.id for item in block.evidence],
            } for block in model.report.blocks],
        },
        "events": [{
            "sequence": event.sequence,
            "message": event.message,
            "created_at": event.created_at,
        } for event in sorted(model.events, key=lambda item: item.sequence)],
    }


def _start(request: Request, run: ResearchRun) -> None:
    """Run the existing orchestrator in-process and persist every state transition."""
    tasks: dict[str, asyncio.Task] = request.app.state.run_tasks
    if run.id in tasks and not tasks[run.id].done():
        return

    async def execute() -> None:
        repository: ResearchRunRepository = request.app.state.repository
        try:
            orchestrator = request.app.state.orchestrator_factory(repository)
            original_update = getattr(orchestrator, "on_update", None)

            async def persist_checkpoint(updated: ResearchRun) -> None:
                if original_update is not None:
                    result = original_update(updated)
                    if inspect.isawaitable(result):
                        await result
                else:
                    await asyncio.to_thread(repository.save_run, updated)
                request.app.state.run_snapshots[run.id] = updated.model_copy(deep=True)

            if hasattr(orchestrator, "on_update"):
                orchestrator.on_update = persist_checkpoint
            await orchestrator.run(run)
        except asyncio.CancelledError:
            checkpoint = request.app.state.run_snapshots.get(run.id, run).model_copy(deep=True)
            if run.id in request.app.state.cancel_requested:
                request.app.state.cancel_requested.discard(run.id)
                checkpoint.status = RunStatus.CANCELLED
                checkpoint.event("研究任务已结束")
                await asyncio.to_thread(repository.save_run, checkpoint)
            else:
                if checkpoint.status is not RunStatus.PAUSED:
                    checkpoint.resume_status = checkpoint.resume_status or checkpoint.status
                    checkpoint.resume_iteration = checkpoint.resume_iteration or checkpoint.iteration
                    checkpoint.status = RunStatus.PAUSED
                    checkpoint.event("后端服务已停止，研究进度已保存；可继续任务")
                    await asyncio.to_thread(repository.save_run, checkpoint)
                logger.info("Research run %s paused at its last persisted checkpoint", run.id)
            raise
        except Exception as exc:
            logger.exception("Research run %s failed during execution", run.id)
            run.status = RunStatus.FAILED
            run.event(f"研究执行失败：{_public_error(exc)}；详细堆栈已记录在后端日志（run_id={run.id}）")
            await asyncio.to_thread(repository.save_run, run)

    task = asyncio.create_task(execute(), name=f"research-{run.id}")
    tasks[run.id] = task
    request.app.state.run_snapshots[run.id] = run.model_copy(deep=True)

    def remove_finished(completed: asyncio.Task) -> None:
        if tasks.get(run.id) is completed:
            tasks.pop(run.id, None)
            request.app.state.run_snapshots.pop(run.id, None)

    task.add_done_callback(remove_finished)


@router.post("", response_model=AcceptedResearchRun, status_code=status.HTTP_202_ACCEPTED)
async def create_research_run(payload: CreateResearchRun, request: Request):
    report_language, language_source = resolve_report_language(
        payload.user_request, payload.report_language
    )
    run = ResearchRun(
        user_request=payload.user_request,
        report_language=report_language,
        report_language_source=language_source,
        max_iterations=payload.max_iterations,
    )
    repository: ResearchRunRepository = request.app.state.repository
    await asyncio.to_thread(repository.save_run, run)
    _start(request, run)
    return {
        "id": run.id,
        "status": run.status.value,
        "report_language": run.report_language,
    }


@router.post("/language-preview", response_model=ReportLanguagePreview)
def preview_report_language(payload: PreviewReportLanguage):
    report_language, language_source = resolve_report_language(
        payload.user_request, payload.report_language
    )
    profile = language_profile(report_language)
    return {
        "tag": profile.tag,
        "name": profile.name,
        "quality": profile.quality,
        "source": language_source,
    }


@router.get("", response_model=ResearchRunList)
def list_research_runs(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, min_length=1, max_length=200),
):
    valid_statuses = {item.value for item in RunStatus} | {"active"}
    if status_filter and status_filter not in valid_statuses:
        raise HTTPException(status_code=422, detail="Invalid research status")
    repository: ResearchRunRepository = request.app.state.repository
    rows = repository.list_runs(
        limit=page_size,
        offset=(page - 1) * page_size,
        status=status_filter,
        search=search,
    )
    total = repository.count_runs(status=status_filter, search=search)
    items = []
    for row in rows:
        profile = language_profile(row["report_language"])
        items.append({
            **row,
            "report_language": profile.tag,
            "report_language_name": profile.name,
            "report_language_quality": profile.quality,
            "report_direction": profile.direction,
        })
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "summary": {
            "total": repository.count_runs(),
            "active": repository.count_runs(status="active"),
            "completed": repository.count_runs(status=RunStatus.COMPLETED.value),
            "needs_human_review": repository.count_runs(
                status=RunStatus.NEEDS_HUMAN_REVIEW.value
            ),
        },
    }


@router.get("/{run_id}", response_model=ResearchRunDetail)
def get_research_run(run_id: str, request: Request):
    model = request.app.state.repository.get_run(run_id)
    if model is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    return _detail(model)


@router.get("/{run_id}/progress", response_model=ResearchProgress)
def get_research_progress(
    run_id: str,
    request: Request,
    after_sequence: int = Query(default=0, ge=0),
):
    progress = request.app.state.repository.get_progress(run_id, after_sequence)
    if progress is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    return progress


@router.get("/{run_id}/events")
async def stream_research_events(
    run_id: str,
    request: Request,
    after_sequence: int = Query(default=0, ge=0),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
):
    repository: ResearchRunRepository = request.app.state.repository
    if last_event_id and last_event_id.isdigit():
        after_sequence = max(after_sequence, int(last_event_id))
    if await asyncio.to_thread(repository.get_progress, run_id, after_sequence) is None:
        raise HTTPException(status_code=404, detail="Research run not found")

    async def events() -> AsyncIterator[str]:
        sequence = after_sequence
        last_state = None
        last_heartbeat = asyncio.get_running_loop().time()
        while not await request.is_disconnected():
            progress = await asyncio.to_thread(repository.get_progress, run_id, sequence)
            if progress is None:
                return

            new_events = progress["events"]
            state_key = (progress["status"], progress["iteration"])
            if new_events or state_key != last_state:
                if new_events:
                    sequence = max(item["sequence"] for item in new_events)
                payload = json.dumps(progress, ensure_ascii=False, default=str)
                yield f"id: {sequence}\nevent: progress\ndata: {payload}\n\n"
                last_state = state_key
                if progress["status"] in SSE_CLOSED_STATUSES:
                    return

            now = asyncio.get_running_loop().time()
            if now - last_heartbeat >= 15:
                yield ": keep-alive\n\n"
                last_heartbeat = now
            await asyncio.sleep(1)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/{run_id}/references/{reference_id}", response_model=CitationReferenceView)
def get_citation_reference(run_id: str, reference_id: str, request: Request):
    reference = request.app.state.repository.get_citation_reference(run_id, reference_id)
    if reference is None:
        raise HTTPException(status_code=404, detail="Citation reference not found")
    return reference


@router.get("/{run_id}/report.md", response_class=PlainTextResponse)
def download_report(run_id: str, request: Request):
    model = request.app.state.repository.get_run(run_id)
    if model is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    if model.report is None:
        raise HTTPException(status_code=409, detail="Report is not ready")
    filename = f"research-{run_id}.md"
    return Response(
        content=model.report.markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_research_run(run_id: str, request: Request):
    active = request.app.state.run_tasks.get(run_id)
    if active is not None and not active.done():
        raise HTTPException(status_code=409, detail="Cancel the active research run before deleting it")
    thread_ids = [
        item["id"]
        for item in request.app.state.follow_up_repository.list_threads(run_id)
    ]
    await cancel_follow_up_tasks(request, thread_ids)
    deleted = await asyncio.to_thread(request.app.state.repository.delete_run, run_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Research run not found")


@router.post("/{run_id}/resume", response_model=AcceptedResearchRun,
             status_code=status.HTTP_202_ACCEPTED)
async def resume_research_run(run_id: str, request: Request):
    repository: ResearchRunRepository = request.app.state.repository
    tasks: dict[str, asyncio.Task] = request.app.state.run_tasks
    active = tasks.get(run_id)
    if active is not None and not active.done():
        model = repository.get_run(run_id)
        if model is None:
            raise HTTPException(status_code=404, detail="Research run not found")
        return {
            "id": run_id,
            "status": model.status,
            "report_language": model.report_language,
        }

    run = await asyncio.to_thread(repository.load_run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    if _can_resume(repository.get_run(run_id)):
        _restore_checkpoint(run)
        run.event(f"继续任务：从第 {run.iteration} 轮之后的未完成阶段继续（{run.status.value}）")
    elif run.status.value in FINAL_STATUSES:
        raise HTTPException(status_code=409, detail="Research run is already finished")
    else:
        raise HTTPException(status_code=409, detail="No resumable checkpoint is available")
    await asyncio.to_thread(repository.save_run, run)
    checkpoint = await asyncio.to_thread(repository.load_run, run_id)
    if checkpoint is None or checkpoint.status is not run.status:
        raise HTTPException(status_code=500, detail="Unable to persist research checkpoint")
    _start(request, run)
    return {
        "id": run.id,
        "status": run.status.value,
        "report_language": run.report_language,
    }


@router.post("/{run_id}/cancel", response_model=AcceptedResearchRun,
             status_code=status.HTTP_202_ACCEPTED)
async def cancel_research_run(run_id: str, request: Request):
    repository: ResearchRunRepository = request.app.state.repository
    model = repository.get_run(run_id)
    if model is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    if model.status in FINAL_STATUSES:
        raise HTTPException(status_code=409, detail="Research run is already finished")

    task = request.app.state.run_tasks.get(run_id)
    if task is not None and not task.done():
        request.app.state.cancel_requested.add(run_id)
        snapshot = request.app.state.run_snapshots.get(run_id)
        if snapshot is not None:
            snapshot.resume_status = RunStatus(model.resume_status or model.status)
            snapshot.resume_iteration = model.resume_iteration
        task.cancel()
    else:
        run = await asyncio.to_thread(repository.load_run, run_id)
        run.status = RunStatus.CANCELLED
        run.event("研究任务已结束")
        await asyncio.to_thread(repository.save_run, run)
    return {
        "id": run_id,
        "status": RunStatus.CANCELLED.value,
        "report_language": model.report_language,
    }
