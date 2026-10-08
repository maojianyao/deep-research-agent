"""FastAPI application entry point. Run with: uvicorn backend.src.api.main:app"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.src.api.research import router as research_router
from backend.src.storage import ResearchRunRepository, create_db_engine, init_db


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


def create_app(engine=None, orchestrator_factory=build_orchestrator) -> FastAPI:
    db_engine = engine or create_db_engine()
    init_db(db_engine)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        tasks = list(_app.state.run_tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            import asyncio
            await asyncio.gather(*tasks, return_exceptions=True)
        db_engine.dispose()

    application = FastAPI(
        title="Deep Research API",
        version="1.0.0",
        lifespan=lifespan,
    )
    application.state.repository = ResearchRunRepository(db_engine)
    application.state.orchestrator_factory = orchestrator_factory
    application.state.run_tasks = {}
    origins = [origin.strip() for origin in os.getenv(
        "FRONTEND_ORIGINS", "http://localhost:3000,http://localhost:5173"
    ).split(",") if origin.strip()]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )
    application.include_router(research_router)

    @application.get("/api/health", tags=["system"])
    def health():
        return {"status": "ok"}

    return application


app = create_app()
