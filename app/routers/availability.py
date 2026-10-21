from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Meeting, User
from app.schemas import AvailabilityResponse, require_aware

router = APIRouter(prefix="/api/availability", tags=["availability"])


@router.get("", response_model=AvailabilityResponse)
def availability(
    start: datetime = Query(...),
    end: datetime = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        start = require_aware(start)
        end = require_aware(end)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if start >= end:
        raise HTTPException(status_code=422, detail="end must be after start")
    meetings = db.scalars(select(Meeting).where(
        Meeting.owner_id == user.id,
        Meeting.status == "scheduled",
        Meeting.start_time < end,
        Meeting.end_time > start,
    ).order_by(Meeting.start_time)).all()
    return {"start": start, "end": end, "available": not meetings, "meetings": meetings}
