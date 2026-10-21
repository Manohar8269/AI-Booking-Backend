from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Approval, User
from app.schemas import ApprovalDecision, ApprovalResponse
from app.services import decide_approval

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get("", response_model=list[ApprovalResponse])
def list_approvals(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return list(db.scalars(select(Approval).where(Approval.owner_id == user.id).order_by(Approval.created_at.desc())))


@router.post("/{approval_id}/decision", response_model=ApprovalResponse)
def decision(
    approval_id: int,
    payload: ApprovalDecision,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    approval = db.scalar(select(Approval).where(Approval.id == approval_id, Approval.owner_id == user.id))
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    result = decide_approval(db, approval, payload.decision)
    db.commit()
    if result.status == "expired":
        raise HTTPException(status_code=410, detail="Approval has expired")
    db.refresh(result)
    return result
