from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EmailAddress = Annotated[str, Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s.]+(?:\.[^@\s.]+)+$")]


def require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Datetime must include a timezone offset")
    return value.astimezone(timezone.utc)


class SignupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailAddress
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailAddress
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    id: int
    name: str
    email: EmailAddress
    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class MeetingCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    location: str | None = Field(default=None, max_length=500)
    attendees: list[str] | str | None = None
    start_time: datetime
    end_time: datetime

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_datetime(cls, value: datetime) -> datetime:
        return require_aware(value)

    @model_validator(mode="after")
    def validate_interval(self):
        if self.start_time >= self.end_time:
            raise ValueError("end_time must be after start_time")
        return self


class MeetingUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    location: str | None = Field(default=None, max_length=500)
    attendees: list[str] | str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_datetime(cls, value: datetime | None) -> datetime | None:
        return require_aware(value) if value is not None else value

    @model_validator(mode="after")
    def validate_interval(self):
        if self.start_time is not None and self.end_time is not None and self.start_time >= self.end_time:
            raise ValueError("end_time must be after start_time")
        return self


class MeetingResponse(BaseModel):
    id: int
    owner_id: int
    title: str
    description: str | None
    location: str | None = None
    attendees: list[str] | str | None = None
    start_time: datetime
    end_time: datetime
    status: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

    @field_validator("start_time", "end_time", "created_at", "updated_at", mode="before")
    @classmethod
    def normalize_output_datetime(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class ApprovalResponse(BaseModel):
    id: int
    meeting_id: int
    meeting_title: str | None = None
    meeting_status: str | None = None
    meeting_start_time: datetime | None = None
    action: str
    payload: dict = Field(default_factory=dict)
    status: str
    expires_at: datetime
    decided_at: datetime | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

    @field_validator("expires_at", "decided_at", "created_at", "meeting_start_time", mode="before")
    @classmethod
    def normalize_output_datetime(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class ApprovalDecision(BaseModel):
    decision: Literal["approve", "reject"]


class CancellationApprovalDescriptor(BaseModel):
    id: int
    meeting_id: int
    status: Literal["pending"]
    expires_at: datetime

    @field_validator("expires_at", mode="before")
    @classmethod
    def normalize_expiry(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class CancellationResult(BaseModel):
    status: Literal["approval_required", "cancelled"]
    meeting_id: int
    lab_mode: Literal["vulnerable"] | None = None
    approval: CancellationApprovalDescriptor | None = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str = Field(default="default", min_length=1, max_length=128)

    @field_validator("conversation_id")
    @classmethod
    def normalize_conversation_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("conversation_id must not be blank")
        return normalized


class ChatResponse(BaseModel):
    reply: str
    mode: str


class AuditResponse(BaseModel):
    id: int
    action: str
    resource_type: str
    resource_id: str
    details: str | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

    @field_validator("created_at", mode="before")
    @classmethod
    def normalize_output_datetime(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class AvailabilityResponse(BaseModel):
    start: datetime
    end: datetime
    available: bool
    meetings: list[MeetingResponse]
