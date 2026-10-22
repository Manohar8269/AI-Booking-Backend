from fastapi import APIRouter, Depends, HTTPException

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Approval, Meeting, User
from app.schemas import ApprovalDecision, ApprovalResponse
from app.services import attach_meeting, decide_approval

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get("", response_model=list[ApprovalResponse])
def list_approvals(db=Depends(get_db), user: User = Depends(get_current_user)):
    approvals = db.find_many(Approval, {"owner_id": user.id}, sort=[("created_at", -1)])
    for approval in approvals:
        meeting = db.find_one(Meeting, {"_id": approval.meeting_id, "owner_id": user.id})
        attach_meeting(approval, meeting)
    return approvals


@router.post("/{approval_id}/decision", response_model=ApprovalResponse)
def decision(
    approval_id: int,
    payload: ApprovalDecision,
    db=Depends(get_db),
    user: User = Depends(get_current_user),
):
    approval = db.find_one(Approval, {"_id": approval_id, "owner_id": user.id})
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    result = decide_approval(db, approval, payload.decision)
    db.commit()
    if result.status == "expired":
        raise HTTPException(status_code=410, detail="Approval has expired")
    return result
