from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Meeting, User
from app.schemas import AvailabilityResponse, require_aware

router = APIRouter(prefix="/api/availability", tags=["availability"])


@router.get("", response_model=AvailabilityResponse)
def availability(
    start: datetime = Query(...),
    end: datetime = Query(...),
    db=Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        start = require_aware(start)
        end = require_aware(end)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if start >= end:
        raise HTTPException(status_code=422, detail="end must be after start")
    meetings = db.find_many(
        Meeting,
        {
            "owner_id": user.id,
            "status": "scheduled",
            "start_time": {"$lt": end},
            "end_time": {"$gt": start},
        },
        sort=[("start_time", 1)],
    )
    return {"start": start, "end": end, "available": not meetings, "meetings": meetings}
