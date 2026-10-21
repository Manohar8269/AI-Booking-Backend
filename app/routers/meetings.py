from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Meeting, User
from app.schemas import CancellationResult, MeetingCreate, MeetingResponse, MeetingUpdate
from app.services import assert_no_conflict, audit, owned_meeting, request_cancellation

router = APIRouter(prefix="/api/meetings", tags=["meetings"])


@router.get("", response_model=list[MeetingResponse])
def list_meetings(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return list(db.scalars(select(Meeting).where(Meeting.owner_id == user.id).order_by(Meeting.start_time)))


@router.post("", response_model=MeetingResponse, status_code=status.HTTP_201_CREATED)
def create_meeting(payload: MeetingCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    assert_no_conflict(db, user.id, payload.start_time, payload.end_time)
    meeting = Meeting(owner_id=user.id, **payload.model_dump())
    db.add(meeting)
    db.flush()
    audit(db, user.id, "meeting.created", "meeting", meeting.id)
    db.commit()
    db.refresh(meeting)
    return meeting


@router.get("/{meeting_id}", response_model=MeetingResponse)
def get_meeting(meeting_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return owned_meeting(db, user.id, meeting_id)


@router.patch("/{meeting_id}", response_model=MeetingResponse)
def update_meeting(
    meeting_id: int,
    payload: MeetingUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    meeting = owned_meeting(db, user.id, meeting_id)
    changes = payload.model_dump(exclude_unset=True)
    start = changes.get("start_time", meeting.start_time)
    end = changes.get("end_time", meeting.end_time)
    if start.tzinfo is None:
        from datetime import timezone
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        from datetime import timezone
        end = end.replace(tzinfo=timezone.utc)
    if start >= end:
        raise HTTPException(status_code=422, detail="end_time must be after start_time")
    assert_no_conflict(db, user.id, start, end, exclude_id=meeting.id)
    for key, value in changes.items():
        setattr(meeting, key, value)
    audit(db, user.id, "meeting.updated", "meeting", meeting.id, {"fields": sorted(changes)})
    db.commit()
    db.refresh(meeting)
    return meeting


@router.delete(
    "/{meeting_id}",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CancellationResult,
    response_model_exclude_none=True,
)
def delete_meeting(meeting_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    meeting = owned_meeting(db, user.id, meeting_id)
    if meeting.status != "scheduled":
        raise HTTPException(status_code=409, detail="Meeting is not scheduled")
    approval = request_cancellation(db, user.id, meeting)
    db.commit()
    db.refresh(approval)
    return {
        "status": "approval_required",
        "meeting_id": meeting.id,
        "approval": {
            "id": approval.id,
            "meeting_id": approval.meeting_id,
            "status": approval.status,
            "expires_at": approval.expires_at,
        },
    }
