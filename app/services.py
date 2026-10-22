import json
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status

from app.config import get_settings
from app.models import Approval, AuditLog, Meeting


def _approval_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=get_settings().approval_ttl_minutes)


def audit(db, actor_id: int, action: str, resource_type: str, resource_id: int | str, details: dict | None = None) -> None:
    db.add(AuditLog(
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id),
        details=json.dumps(details, sort_keys=True) if details else None,
    ))


def owned_meeting(db, user_id: int, meeting_id: int) -> Meeting:
    meeting = db.find_one(Meeting, {"_id": meeting_id, "owner_id": user_id})
    if meeting is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    return meeting


def assert_no_conflict(
    db, owner_id: int, start_time: datetime, end_time: datetime, exclude_id: int | None = None
) -> None:
    query = {
        "owner_id": owner_id,
        "status": "scheduled",
        "start_time": {"$lt": end_time},
        "end_time": {"$gt": start_time},
    }
    if exclude_id is not None:
        query["_id"] = {"$ne": exclude_id}
    if db.find_one(Meeting, query) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Meeting conflicts with an existing meeting")


def request_cancellation(db, user_id: int, meeting: Meeting) -> Approval:
    now = datetime.now(timezone.utc)
    existing = db.find_one(
        Approval,
        {"owner_id": user_id, "meeting_id": meeting.id, "status": "pending"},
        sort=[("created_at", -1)],
    )
    if existing is not None:
        expiry = existing.expires_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry > now:
            return existing
        existing.status = "expired"
        existing.decided_at = now
        audit(db, user_id, "approval.expired", "approval", existing.id)
    approval = Approval(
        owner_id=user_id,
        meeting_id=meeting.id,
        action="cancel_meeting",
        status="pending",
        expires_at=_approval_expiry(),
    )
    db.add(approval)
    db.flush()
    audit(db, user_id, "meeting.cancellation_requested", "meeting", meeting.id, {"approval_id": approval.id})
    return approval


def attach_meeting(approval: Approval, meeting: Meeting | None) -> Approval:
    approval.meeting_title = meeting.title if meeting else None
    approval.meeting_status = meeting.status if meeting else None
    approval.meeting_start_time = meeting.start_time if meeting else None
    return approval


def decide_approval(db, approval: Approval, decision: str) -> Approval:
    now = datetime.now(timezone.utc)
    expires_at = approval.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if approval.status != "pending":
        raise HTTPException(status_code=409, detail="Approval has already been decided")
    if expires_at <= now:
        approval.status = "expired"
        approval.decided_at = now
        audit(db, approval.owner_id, "approval.expired", "approval", approval.id)
        return attach_meeting(approval, db.get(Meeting, approval.meeting_id))
    meeting = db.get(Meeting, approval.meeting_id)
    if meeting is None or meeting.owner_id != approval.owner_id:
        raise HTTPException(status_code=404, detail="Meeting not found")
    approval.status = "approved" if decision == "approve" else "rejected"
    approval.decided_at = now
    if decision == "approve":
        meeting.status = "cancelled"
        meeting.updated_at = now
        audit(db, approval.owner_id, "meeting.cancelled", "meeting", meeting.id, {"approval_id": approval.id})
    audit(db, approval.owner_id, f"approval.{approval.status}", "approval", approval.id)
    return attach_meeting(approval, meeting)
