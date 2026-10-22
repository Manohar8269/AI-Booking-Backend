from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.schemas import LoginRequest, SignupRequest, TokenResponse, UserResponse
from app.security import create_access_token, hash_password, verify_password
from app.services import audit

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, db=Depends(get_db)):
    email = str(payload.email).lower()
    if db.find_one(User, {"email": email}):
        raise HTTPException(status_code=409, detail="Email is already registered")
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name cannot be blank")
    user = User(name=name, email=email, password_hash=hash_password(payload.password))
    db.add(user)
    db.flush()
    try:
        db.commit()
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Email is already registered") from None
    audit(db, user.id, "auth.signup", "user", user.id)
    db.commit()
    return user


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db=Depends(get_db)):
    user = db.find_one(User, {"email": str(payload.email).lower()})
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user.id)
    audit(db, user.id, "auth.login", "user", user.id)
    db.commit()
    return {"access_token": token, "token_type": "bearer", "user": user}


@router.get("/me", response_model=UserResponse)
def current_user(user: User = Depends(get_current_user)):
    return user
