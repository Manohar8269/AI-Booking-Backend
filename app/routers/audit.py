from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import AuditLog, User
from app.schemas import AuditResponse

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=list[AuditResponse])
def list_audit(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return list(db.scalars(select(AuditLog).where(AuditLog.actor_id == user.id).order_by(AuditLog.created_at.desc()).limit(200)))
