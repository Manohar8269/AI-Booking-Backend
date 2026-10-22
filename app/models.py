from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import ClassVar


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class User:
    collection: ClassVar[str] = "users"
    id: int | None = None
    name: str = ""
    email: str = ""
    password_hash: str = ""
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class Meeting:
    collection: ClassVar[str] = "meetings"
    id: int | None = None
    owner_id: int = 0
    title: str = ""
    description: str | None = None
    location: str | None = None
    attendees: list[str] | str | None = None
    start_time: datetime = field(default_factory=utc_now)
    end_time: datetime = field(default_factory=utc_now)
    status: str = "scheduled"
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class Approval:
    collection: ClassVar[str] = "approvals"
    id: int | None = None
    owner_id: int = 0
    meeting_id: int = 0
    action: str = "cancel_meeting"
    status: str = "pending"
    expires_at: datetime = field(default_factory=utc_now)
    decided_at: datetime | None = None
    created_at: datetime = field(default_factory=utc_now)
    meeting_title: str | None = None
    meeting_status: str | None = None
    meeting_start_time: datetime | None = None


@dataclass
class AuditLog:
    collection: ClassVar[str] = "audit_logs"
    id: int | None = None
    actor_id: int = 0
    action: str = ""
    resource_type: str = ""
    resource_id: str = ""
    details: str | None = None
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class ChatPendingAction:
    collection: ClassVar[str] = "chat_pending_actions"
    id: int | None = None
    owner_id: int = 0
    action: str = ""
    payload: dict = field(default_factory=dict)
    expires_at: datetime = field(default_factory=utc_now)
    created_at: datetime = field(default_factory=utc_now)
