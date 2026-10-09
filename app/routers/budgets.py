from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..constants import CATEGORIES
from ..database import get_db
from ..deps import get_current_user
from ..models import Budget, User
from ..schemas import BudgetIn, BudgetOut
from ..services.finance import budget_out, budgets_for_month, month_bounds, spent_by_category

router = APIRouter(prefix="/budgets", tags=["budgets"])


def _check(category: str) -> str:
    if category not in CATEGORIES:
        raise HTTPException(422, f"category must be one of {CATEGORIES}")
    return category


@router.get("", response_model=list[BudgetOut])
def list_budgets(
    month: str | None = Query(default=None, description="YYYY-MM, defaults to the current month"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    start, end, _ = month_bounds(month)
    return budgets_for_month(db, user, start, end)


@router.put("/{category}", response_model=BudgetOut, summary="Create or update a category budget")
def upsert_budget(category: str, body: BudgetIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _check(category)
    b = db.scalars(select(Budget).where(Budget.user_id == user.id, Budget.category == category)).first()
    if b:
        b.limit, b.alert_threshold = body.limit, body.alert_threshold
    else:
        b = Budget(user_id=user.id, category=category, limit=body.limit, alert_threshold=body.alert_threshold)
        db.add(b)
    db.commit()
    start, end, _ = month_bounds(None)
    return budget_out(b, spent_by_category(db, user, start, end).get(category, 0.0))


@router.delete("/{category}", status_code=204)
def delete_budget(category: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    b = db.scalars(select(Budget).where(Budget.user_id == user.id, Budget.category == category)).first()
    if not b:
        raise HTTPException(404, "Budget not found")
    db.delete(b)
    db.commit()
