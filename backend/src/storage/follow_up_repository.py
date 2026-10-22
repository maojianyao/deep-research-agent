"""Persistence for report-bound follow-up threads, messages, and stream events."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, selectinload

from backend.src.research.schemas import new_id

from .models import FollowUpEventModel, FollowUpMessageModel, FollowUpThreadModel


class FollowUpBusyError(Exception):
    pass


class FollowUpNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class StartedFollowUp:
    thread: dict
    assistant_message_id: int
    history: list[dict]


class FollowUpRepository:
    def __init__(self, engine: Engine):
        self.engine = engine

    def start_thread(self, *, run_id: str, anchor: dict,
                     question: str) -> StartedFollowUp:
        thread_id = new_id("followup")
        with Session(self.engine) as session, session.begin():
            thread = FollowUpThreadModel(
                id=thread_id,
                run_id=run_id,
                selection_text=anchor["text"],
                selection_start=anchor["start"],
                selection_end=anchor["end"],
                selection_prefix=anchor["prefix"],
                selection_suffix=anchor["suffix"],
                report_digest=anchor["report_digest"],
            )
            user = FollowUpMessageModel(
                role="user", sequence=1, content=question, status="completed",
            )
            assistant = FollowUpMessageModel(
                role="assistant", sequence=2, content="", status="generating",
            )
            thread.messages = [user, assistant]
            session.add(thread)
            session.flush()
            thread.events = [
                FollowUpEventModel(
                    sequence=1,
                    event_type="status",
                    message_id=assistant.id,
                    status="generating",
                ),
            ]
            session.flush()
            return StartedFollowUp(
                thread=self._to_dict(thread, stream_cursor=1),
                assistant_message_id=assistant.id,
                history=[{"role": "user", "content": question}],
            )

    def append_question(self, *, run_id: str, thread_id: str,
                        question: str) -> StartedFollowUp:
        with Session(self.engine) as session, session.begin():
            thread = session.scalar(
                select(FollowUpThreadModel)
                .where(
                    FollowUpThreadModel.id == thread_id,
                    FollowUpThreadModel.run_id == run_id,
                )
                .options(selectinload(FollowUpThreadModel.messages))
            )
            if thread is None:
                raise FollowUpNotFoundError
            if any(
                message.role == "assistant" and message.status == "generating"
                for message in thread.messages
            ):
                raise FollowUpBusyError

            message_sequence = max(
                (message.sequence for message in thread.messages), default=0
            )
            user = FollowUpMessageModel(
                role="user",
                sequence=message_sequence + 1,
                content=question,
                status="completed",
            )
            assistant = FollowUpMessageModel(
                role="assistant",
                sequence=message_sequence + 2,
                content="",
                status="generating",
            )
            thread.messages.extend([user, assistant])
            history = [
                {"role": item.role, "content": item.content}
                for item in sorted(thread.messages, key=lambda item: item.sequence)
                if item.status == "completed"
            ][-40:]
            session.flush()
            event_cursor = self._next_event_sequence(session, thread_id)
            thread.events.append(FollowUpEventModel(
                sequence=event_cursor,
                event_type="status",
                message_id=assistant.id,
                status="generating",
            ))
            session.flush()
            return StartedFollowUp(
                thread=self._to_dict(thread, stream_cursor=event_cursor),
                assistant_message_id=assistant.id,
                history=history,
            )

    def get_thread(self, run_id: str, thread_id: str) -> dict | None:
        with Session(self.engine) as session:
            thread = session.scalar(
                select(FollowUpThreadModel)
                .where(
                    FollowUpThreadModel.id == thread_id,
                    FollowUpThreadModel.run_id == run_id,
                )
                .options(selectinload(FollowUpThreadModel.messages))
            )
            if thread is None:
                return None
            return self._to_dict(thread, self._thread_cursor(session, thread_id))

    def list_threads(self, run_id: str) -> list[dict]:
        query = (
            select(FollowUpThreadModel)
            .where(FollowUpThreadModel.run_id == run_id)
            .options(selectinload(FollowUpThreadModel.messages))
            .order_by(FollowUpThreadModel.created_at, FollowUpThreadModel.id)
        )
        with Session(self.engine) as session:
            return [
                self._to_dict(model, self._thread_cursor(session, model.id))
                for model in session.scalars(query).all()
            ]

    def append_delta(self, thread_id: str, message_id: int, content: str) -> int:
        with Session(self.engine) as session, session.begin():
            message = session.get(FollowUpMessageModel, message_id)
            if message is None or message.thread_id != thread_id:
                raise FollowUpNotFoundError
            if message.status != "generating":
                return self._next_event_sequence(session, thread_id) - 1
            message.content = f"{message.content}{content}"
            sequence = self._next_event_sequence(session, thread_id)
            session.add(FollowUpEventModel(
                thread_id=thread_id,
                sequence=sequence,
                event_type="delta",
                message_id=message_id,
                content=content,
                status="generating",
            ))
            return sequence

    def complete_message(self, thread_id: str, message_id: int) -> int:
        return self._finish_message(
            thread_id, message_id, status="completed", event_type="completed",
        )

    def fail_message(self, thread_id: str, message_id: int,
                     error_message: str) -> int:
        return self._finish_message(
            thread_id,
            message_id,
            status="failed",
            event_type="failed",
            error_code="generation_failed",
            error_message=error_message,
        )

    def interrupt_message(self, thread_id: str, message_id: int,
                          error_message: str = "Backend stopped before the answer completed") -> int:
        return self._finish_message(
            thread_id,
            message_id,
            status="interrupted",
            event_type="interrupted",
            error_code="generation_interrupted",
            error_message=error_message,
        )

    def interrupt_generating_messages(self) -> int:
        with Session(self.engine) as session, session.begin():
            messages = session.scalars(select(FollowUpMessageModel).where(
                FollowUpMessageModel.role == "assistant",
                FollowUpMessageModel.status == "generating",
            )).all()
            for message in messages:
                message.status = "interrupted"
                message.error_code = "generation_interrupted"
                message.error_message = "Backend restarted before the answer completed"
                session.add(FollowUpEventModel(
                    thread_id=message.thread_id,
                    sequence=self._next_event_sequence(session, message.thread_id),
                    event_type="interrupted",
                    message_id=message.id,
                    status="interrupted",
                    error_code=message.error_code,
                    error_message=message.error_message,
                ))
            return len(messages)

    def list_events_after(self, thread_id: str, after_sequence: int) -> list[dict]:
        query = (
            select(FollowUpEventModel)
            .where(
                FollowUpEventModel.thread_id == thread_id,
                FollowUpEventModel.sequence > after_sequence,
            )
            .order_by(FollowUpEventModel.sequence)
        )
        with Session(self.engine) as session:
            return [self._event_dict(item) for item in session.scalars(query).all()]

    def has_generating_message(self, thread_id: str) -> bool:
        with Session(self.engine) as session:
            return session.scalar(select(func.count()).select_from(FollowUpMessageModel).where(
                FollowUpMessageModel.thread_id == thread_id,
                FollowUpMessageModel.role == "assistant",
                FollowUpMessageModel.status == "generating",
            )) > 0

    def _finish_message(self, thread_id: str, message_id: int, *, status: str,
                        event_type: str, error_code: str | None = None,
                        error_message: str | None = None) -> int:
        with Session(self.engine) as session, session.begin():
            message = session.get(FollowUpMessageModel, message_id)
            if message is None or message.thread_id != thread_id:
                raise FollowUpNotFoundError
            if message.status != "generating":
                return self._next_event_sequence(session, thread_id) - 1
            message.status = status
            message.error_code = error_code
            message.error_message = error_message
            sequence = self._next_event_sequence(session, thread_id)
            session.add(FollowUpEventModel(
                thread_id=thread_id,
                sequence=sequence,
                event_type=event_type,
                message_id=message_id,
                status=status,
                error_code=error_code,
                error_message=error_message,
            ))
            return sequence

    @staticmethod
    def _next_event_sequence(session: Session, thread_id: str) -> int:
        current = session.scalar(select(func.max(FollowUpEventModel.sequence)).where(
            FollowUpEventModel.thread_id == thread_id
        ))
        return (current or 0) + 1

    @staticmethod
    def _thread_cursor(session: Session, thread_id: str) -> int:
        return session.scalar(select(func.max(FollowUpEventModel.sequence)).where(
            FollowUpEventModel.thread_id == thread_id
        )) or 0

    @staticmethod
    def _event_dict(event: FollowUpEventModel) -> dict:
        return {
            "thread_id": event.thread_id,
            "sequence": event.sequence,
            "type": event.event_type,
            "message_id": event.message_id,
            "content": event.content,
            "status": event.status,
            "error_code": event.error_code,
            "error_message": event.error_message,
            "created_at": event.created_at,
        }

    @staticmethod
    def _to_dict(model: FollowUpThreadModel, stream_cursor: int) -> dict:
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
            "stream_cursor": stream_cursor,
            "created_at": model.created_at,
            "updated_at": model.updated_at,
        }
