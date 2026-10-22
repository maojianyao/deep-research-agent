"""Persistence for report-bound follow-up threads and their messages."""

from __future__ import annotations

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, selectinload

from backend.src.research.schemas import new_id

from .models import FollowUpMessageModel, FollowUpThreadModel


class FollowUpRepository:
    def __init__(self, engine: Engine):
        self.engine = engine

    def create_thread(self, *, run_id: str, anchor: dict, question: str,
                      answer: str) -> dict:
        thread_id = new_id("followup")
        with Session(self.engine) as session, session.begin():
            model = FollowUpThreadModel(
                id=thread_id,
                run_id=run_id,
                selection_text=anchor["text"],
                selection_start=anchor["start"],
                selection_end=anchor["end"],
                selection_prefix=anchor["prefix"],
                selection_suffix=anchor["suffix"],
                report_digest=anchor["report_digest"],
            )
            model.messages = [
                FollowUpMessageModel(
                    role="user", sequence=1, content=question, status="completed",
                ),
                FollowUpMessageModel(
                    role="assistant", sequence=2, content=answer, status="completed",
                ),
            ]
            session.add(model)
            session.flush()
            return self._to_dict(model)

    def list_threads(self, run_id: str) -> list[dict]:
        query = (
            select(FollowUpThreadModel)
            .where(FollowUpThreadModel.run_id == run_id)
            .options(selectinload(FollowUpThreadModel.messages))
            .order_by(FollowUpThreadModel.created_at, FollowUpThreadModel.id)
        )
        with Session(self.engine) as session:
            return [self._to_dict(model) for model in session.scalars(query).all()]

    @staticmethod
    def _to_dict(model: FollowUpThreadModel) -> dict:
        return {
            "id": model.id,
            "run_id": model.run_id,
            "anchor": {
                "text": model.selection_text,
                "start": model.selection_start,
                "end": model.selection_end,
                "prefix": model.selection_prefix,
                "suffix": model.selection_suffix,
                "report_digest": model.report_digest,
            },
            "messages": [{
                "id": item.id,
                "role": item.role,
                "sequence": item.sequence,
                "content": item.content,
                "status": item.status,
                "error_code": item.error_code,
                "error_message": item.error_message,
                "created_at": item.created_at,
            } for item in model.messages],
            "created_at": model.created_at,
            "updated_at": model.updated_at,
        }
