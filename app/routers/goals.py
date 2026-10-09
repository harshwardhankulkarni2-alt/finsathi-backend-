from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Goal, User
from ..schemas import ContributeIn, GoalCreate, GoalOut, GoalUpdate

router = APIRouter(prefix="/goals", tags=["goals"])


def _out(g: Goal) -> GoalOut:
    out = GoalOut.model_validate(g)
    out.percent_complete = round(min(100.0, g.current / g.target * 100), 1) if g.target else 0.0
    return out


def _owned(db: Session, user: User, goal_id: int) -> Goal:
    g = db.get(Goal, goal_id)
    if not g or g.user_id != user.id:
        raise HTTPException(404, "Goal not found")
    return g


@router.get("", response_model=list[GoalOut])
def list_goals(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [_out(g) for g in db.scalars(select(Goal).where(Goal.user_id == user.id).order_by(Goal.id)).all()]


@router.post("", response_model=GoalOut, status_code=201)
def create_goal(body: GoalCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    g = Goal(user_id=user.id, **body.model_dump())
    db.add(g)
    db.commit()
    return _out(g)


@router.patch("/{goal_id}", response_model=GoalOut)
def update_goal(goal_id: int, body: GoalUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    g = _owned(db, user, goal_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(g, k, v)
    db.commit()
    return _out(g)


@router.post("/{goal_id}/contribute", response_model=GoalOut)
def contribute(goal_id: int, body: ContributeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    g = _owned(db, user, goal_id)
    g.current = round(g.current + body.amount, 2)
    db.commit()
    return _out(g)


@router.delete("/{goal_id}", status_code=204)
def delete_goal(goal_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(_owned(db, user, goal_id))
    db.commit()
