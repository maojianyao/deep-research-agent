"""REST endpoints for creating and browsing long-running research jobs."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import PlainTextResponse

from backend.src.research.schemas import ResearchRun, RunStatus
from backend.src.storage.repository import ResearchRunRepository
from .schemas import (
    AcceptedResearchRun, CreateResearchRun, ResearchProgress, ResearchRunDetail, ResearchRunList,
)


router = APIRouter(prefix="/api/research-runs", tags=["research"])
TERMINAL_STATUSES = {RunStatus.COMPLETED.value, RunStatus.FAILED.value,
                     RunStatus.NEEDS_HUMAN_REVIEW.value, RunStatus.CANCELLED.value}


def _source(source) -> dict:
    return {
        "url": source.url,
        "title": source.title,
        "publisher": source.publisher,
        "published_at": source.published_at,
        "source_type": source.source_type,
    }


def _detail(model) -> dict:
    critiques = sorted(model.critiques, key=lambda item: item.iteration)
    return {
        "id": model.id,
        "user_request": model.user_request,
        "status": model.status,
        "iteration": model.iteration,
        "max_iterations": model.max_iterations,
        "created_at": model.created_at,
        "updated_at": model.updated_at,
        "plan": None if model.plan is None else {
            "research_question": model.plan.research_question,
            "scope": model.plan.scope,
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
            "markdown": model.report.markdown,
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
            await orchestrator.run(run)
        except asyncio.CancelledError:
            run.status = RunStatus.CANCELLED
            run.event("研究任务已取消")
            await asyncio.to_thread(repository.save_run, run)
            raise
        except Exception:
            run.status = RunStatus.FAILED
            run.event("研究执行异常，任务已终止")
            await asyncio.to_thread(repository.save_run, run)

    task = asyncio.create_task(execute(), name=f"research-{run.id}")
    tasks[run.id] = task

    def remove_finished(completed: asyncio.Task) -> None:
        if tasks.get(run.id) is completed:
            tasks.pop(run.id, None)

    task.add_done_callback(remove_finished)


@router.post("", response_model=AcceptedResearchRun, status_code=status.HTTP_202_ACCEPTED)
async def create_research_run(payload: CreateResearchRun, request: Request):
    run = ResearchRun(user_request=payload.user_request, max_iterations=payload.max_iterations)
    repository: ResearchRunRepository = request.app.state.repository
    await asyncio.to_thread(repository.save_run, run)
    _start(request, run)
    return {"id": run.id, "status": run.status.value}


@router.get("", response_model=ResearchRunList)
def list_research_runs(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, min_length=1, max_length=200),
):
    if status_filter and status_filter not in {item.value for item in RunStatus}:
        raise HTTPException(status_code=422, detail="Invalid research status")
    repository: ResearchRunRepository = request.app.state.repository
    rows = repository.list_runs(
        limit=page_size,
        offset=(page - 1) * page_size,
        status=status_filter,
        search=search,
    )
    total = repository.count_runs(status=status_filter, search=search)
    return {"items": rows, "total": total, "page": page, "page_size": page_size}


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
        return {"id": run_id, "status": model.status}

    run = await asyncio.to_thread(repository.load_run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    if run.status.value in TERMINAL_STATUSES:
        raise HTTPException(status_code=409, detail="Research run is already finished")
    _start(request, run)
    return {"id": run.id, "status": run.status.value}


@router.post("/{run_id}/cancel", response_model=AcceptedResearchRun,
             status_code=status.HTTP_202_ACCEPTED)
async def cancel_research_run(run_id: str, request: Request):
    repository: ResearchRunRepository = request.app.state.repository
    model = repository.get_run(run_id)
    if model is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    if model.status in TERMINAL_STATUSES:
        raise HTTPException(status_code=409, detail="Research run is already finished")

    task = request.app.state.run_tasks.get(run_id)
    if task is not None and not task.done():
        task.cancel()
    else:
        run = await asyncio.to_thread(repository.load_run, run_id)
        run.status = RunStatus.CANCELLED
        run.event("研究任务已取消")
        await asyncio.to_thread(repository.save_run, run)
    return {"id": run_id, "status": RunStatus.CANCELLED.value}
