"""FastAPI application entry point. Run with: uvicorn backend.main:app"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.src.api.follow_ups import router as follow_up_router
from backend.src.api.research import router as research_router
from backend.src.config import get_config
from backend.src.services.follow_up import LazyFollowUpAnswerer, LLMFollowUpAnswerer
from backend.src.storage import (
    FollowUpRepository, ResearchRunRepository, create_db_engine, init_db,
)
from backend.src.utils.logger import get_logger

conf = get_config()
logger = get_logger(__name__)

def build_orchestrator(repository: ResearchRunRepository):
    from backend.src.research.agents import (
        CriticAgent, EvidenceReviewerAgent, PlannerAgent, ResearcherAgent,
        SynthesizerAgent, WriterAgent,
    )
    from backend.src.research.orchestrator import ResearchOrchestrator
    from backend.src.services.llm import get_llm
    from backend.src.services.search import (
        duckduckgo_search, exa_search, parallel_search, tavily_search, youcom_search,
    )

    searches = [duckduckgo_search]
    for env_key, search in (
        ("TAVILY_API_KEY", tavily_search),
        ("PARALLEL_API_KEY", parallel_search),
        ("YDC_API_KEY", youcom_search),
        ("EXA_API_KEY", exa_search),
    ):
        if os.getenv(env_key):
            searches.append(search)

    orchestrator = ResearchOrchestrator(
        PlannerAgent(get_llm()),
        ResearcherAgent(get_llm(), searches),
        EvidenceReviewerAgent(get_llm()),
        SynthesizerAgent(get_llm()),
        CriticAgent(get_llm()),
        WriterAgent(get_llm()),
    )

    async def persist(run) -> None:
        import asyncio
        await asyncio.to_thread(repository.save_run, run)

    orchestrator.on_update = persist
    return orchestrator


def build_follow_up_answerer():
    from backend.src.services.llm import get_llm
    return LazyFollowUpAnswerer(lambda: LLMFollowUpAnswerer(get_llm()))


def create_app(engine=None, orchestrator_factory=build_orchestrator,
               follow_up_answerer_factory=build_follow_up_answerer) -> FastAPI:
    db_engine = engine or create_db_engine()
    init_db(db_engine)
    repository = ResearchRunRepository(db_engine)
    follow_up_repository = FollowUpRepository(db_engine)
    repository.pause_interrupted_runs()
    follow_up_repository.interrupt_generating_messages()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        tasks = list(_app.state.run_tasks.values())
        import asyncio
        from backend.src.research.schemas import RunStatus

        for run_id, task in list(_app.state.run_tasks.items()):
            if task.done() or run_id in _app.state.cancel_requested:
                continue
            run = _app.state.run_snapshots.get(run_id)
            if run is not None:
                if run.resume_status is None:
                    run.resume_status = run.status
                    run.resume_iteration = run.iteration
                run.status = RunStatus.PAUSED
                if not run.events or not run.events[-1].startswith("后端服务已停止"):
                    run.event("后端服务已停止，研究进度已保存；可继续任务")
                await asyncio.to_thread(repository.save_run, run)
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        follow_up_tasks = list(_app.state.follow_up_tasks.values())
        for task in follow_up_tasks:
            task.cancel()
        if follow_up_tasks:
            await asyncio.gather(*follow_up_tasks, return_exceptions=True)
        db_engine.dispose()

    application = FastAPI(
        title="Deep Research API",
        version="1.0.0",
        lifespan=lifespan,
    )
    application.state.repository = repository
    application.state.follow_up_repository = follow_up_repository
    application.state.follow_up_answerer = follow_up_answerer_factory()
    application.state.orchestrator_factory = orchestrator_factory
    application.state.run_tasks = {}
    application.state.run_snapshots = {}
    application.state.cancel_requested = set()
    application.state.follow_up_tasks = {}
    application.state.follow_up_locks = {}
    origins = [origin.strip() for origin in conf.cors_origins.split(",") if origin.strip()]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )
    application.include_router(research_router)
    application.include_router(follow_up_router)

    @application.get("/api/health", tags=["system"])
    def health():
        return {"status": "ok"}

    @application.get("/", include_in_schema=False)
    def root():
        return {"message": "Deep Research API", "docs": "/docs"}

    return application


app = create_app()


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=conf.host,
        port=conf.port,
        reload=True
    )
