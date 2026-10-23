"""Request and response contracts for report follow-up threads."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ReportSelectionAnchor(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    prefix: str = Field(default="", max_length=200)
    suffix: str = Field(default="", max_length=200)
    report_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class CreateFollowUpThread(BaseModel):
    anchor: ReportSelectionAnchor
    question: str = Field(min_length=1, max_length=2000)


class AppendFollowUpQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class UpdateFollowUpState(BaseModel):
    minimized: bool


class FollowUpMessageView(BaseModel):
    id: int
    role: Literal["user", "assistant"]
    sequence: int
    content: str
    status: str
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime


class FollowUpThreadView(BaseModel):
    id: str
    run_id: str
    anchor: ReportSelectionAnchor
    messages: list[FollowUpMessageView]
    stream_cursor: int
    is_minimized: bool
    created_at: datetime
    updated_at: datetime


class FollowUpThreadList(BaseModel):
    items: list[FollowUpThreadView]
