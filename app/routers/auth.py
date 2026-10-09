from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..constants import DEFAULT_BUDGET_LIMITS
from ..database import get_db
from ..deps import get_current_user
from ..models import Account, Budget, User
from ..schemas import LoginIn, SignupIn, TokenOut, UserOut, UserUpdate
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_for(user: User) -> TokenOut:
    return TokenOut(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.post("/signup", response_model=TokenOut, status_code=201)
def signup(body: SignupIn, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.scalars(select(User).where(User.email == email)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = User(
        name=body.name.strip(),
        email=email,
        password_hash=hash_password(body.password),
        min_reserve=get_settings().default_min_reserve,
    )
    db.add(user)
    db.flush()
    db.add(Account(user_id=user.id, name="Main Account", starting_balance=body.starting_balance))
    for cat, limit in DEFAULT_BUDGET_LIMITS.items():
        db.add(Budget(user_id=user.id, category=cat, limit=limit, alert_threshold=80))
    db.commit()
    return _token_for(user)


def _authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalars(select(User).where(User.email == email.lower())).first()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    return user


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    return _token_for(_authenticate(db, body.email, body.password))


@router.post("/token", include_in_schema=True, summary="OAuth2 form login (used by the Swagger 'Authorize' button)")
def token(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = _authenticate(db, form.username, form.password)
    return {"access_token": create_access_token(user.id), "token_type": "bearer"}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.patch("/me", response_model=UserOut)
def update_me(body: UserUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.name is not None:
        user.name = body.name.strip()
    if body.min_reserve is not None:
        user.min_reserve = body.min_reserve
    db.commit()
    return user
