from fastapi import APIRouter, Depends

from app.database import get_db
from app.dependencies import get_current_user
from app.models import AuditLog, User
from app.schemas import AuditResponse

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=list[AuditResponse])
def list_audit(db=Depends(get_db), user: User = Depends(get_current_user)):
    return db.find_many(AuditLog, {"actor_id": user.id}, sort=[("created_at", -1)], limit=200)
