from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Goal, User
from ..schemas import AssistantIn, AssistantOut, Insight, SummaryOut
from ..services import insights
from ..services.finance import compute_summary

router = APIRouter(tags=["dashboard"])

MONTH_Q = Query(default=None, description="YYYY-MM, defaults to the current month")


@router.get("/summary", response_model=SummaryOut, summary="Balance, income, expenses, savings, Safe-to-Spend, budgets")
def summary(month: str | None = MONTH_Q, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return compute_summary(db, user, month)


@router.get("/insights", response_model=list[Insight])
def get_insights(month: str | None = MONTH_Q, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    goals = db.scalars(select(Goal).where(Goal.user_id == user.id)).all()
    return insights.build_insights(compute_summary(db, user, month), goals)


@router.post("/assistant", response_model=AssistantOut, summary="Answers questions using the user's real data")
def assistant(body: AssistantIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    goals = db.scalars(select(Goal).where(Goal.user_id == user.id)).all()
    return AssistantOut(reply=insights.answer(body.message, compute_summary(db, user, None), goals))
