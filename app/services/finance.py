"""Financial calculations shared by the routers (balance, budgets, safe-to-spend)."""
from __future__ import annotations

import calendar
import re
from datetime import date

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Account, Budget, Goal, ImportBatch, Transaction, User
from ..schemas import BudgetAlert, BudgetOut


def f(x) -> float:
    return round(float(x or 0), 2)


def month_bounds(month: str | None) -> tuple[date, date, str]:
    """'YYYY-MM' -> (first day, first day of next month, label). Defaults to the current month."""
    if month is None:
        today = date.today()
        year, mon = today.year, today.month
    else:
        m = re.fullmatch(r"(\d{4})-(\d{2})", month)
        if not m or not 1 <= int(m.group(2)) <= 12:
            raise HTTPException(422, "month must be in YYYY-MM format")
        year, mon = int(m.group(1)), int(m.group(2))
    start = date(year, mon, 1)
    end = date(year + (mon == 12), (mon % 12) + 1, 1)
    return start, end, f"{year:04d}-{mon:02d}"


def default_account(db: Session, user: User) -> Account:
    acc = db.scalars(select(Account).where(Account.user_id == user.id).order_by(Account.id)).first()
    if not acc:
        acc = Account(user_id=user.id, name="Main Account", starting_balance=0)
        db.add(acc)
        db.flush()
    return acc


def get_owned_account(db: Session, user: User, account_id: int | None) -> Account:
    if account_id is None:
        return default_account(db, user)
    acc = db.get(Account, account_id)
    if not acc or acc.user_id != user.id:
        raise HTTPException(404, "Account not found")
    return acc


def account_balance(db: Session, account: Account) -> float:
    total = db.scalar(select(func.coalesce(func.sum(Transaction.amount), 0)).where(Transaction.account_id == account.id))
    return f(float(account.starting_balance or 0) + float(total or 0))


def total_balance(db: Session, user: User) -> float:
    start = db.scalar(select(func.coalesce(func.sum(Account.starting_balance), 0)).where(Account.user_id == user.id))
    txns = db.scalar(select(func.coalesce(func.sum(Transaction.amount), 0)).where(Transaction.user_id == user.id))
    return f(float(start or 0) + float(txns or 0))


def spent_by_category(db: Session, user: User, start: date, end: date) -> dict[str, float]:
    rows = db.execute(
        select(Transaction.category, func.sum(Transaction.amount))
        .where(Transaction.user_id == user.id, Transaction.amount < 0, Transaction.date >= start, Transaction.date < end)
        .group_by(Transaction.category)
    ).all()
    return {cat: f(abs(float(total))) for cat, total in rows}


def budget_status(limit: float, spent: float, threshold: int) -> str:
    if limit <= 0:
        return "ok"
    if spent > limit:
        return "exceeded"
    if spent / limit * 100 >= threshold:
        return "warning"
    return "ok"


def budget_out(b: Budget, spent: float) -> BudgetOut:
    pct = round(spent / b.limit * 100, 1) if b.limit else 0.0
    return BudgetOut(
        category=b.category,
        limit=b.limit,
        alert_threshold=b.alert_threshold,
        spent=spent,
        remaining=round(b.limit - spent, 2),
        percent_used=pct,
        status=budget_status(b.limit, spent, b.alert_threshold),
    )


def budgets_for_month(db: Session, user: User, start: date, end: date) -> list[BudgetOut]:
    spent = spent_by_category(db, user, start, end)
    budgets = db.scalars(select(Budget).where(Budget.user_id == user.id).order_by(Budget.id)).all()
    return [budget_out(b, spent.get(b.category, 0.0)) for b in budgets]


def budget_alert_for(db: Session, user: User, category: str, on: date) -> BudgetAlert | None:
    """Alert for the category's budget in the month of `on` (same thresholds as the frontend toasts)."""
    b = db.scalars(select(Budget).where(Budget.user_id == user.id, Budget.category == category)).first()
    if not b:
        return None
    start, end, _ = month_bounds(on.strftime("%Y-%m"))
    spent = spent_by_category(db, user, start, end).get(category, 0.0)
    status = budget_status(b.limit, spent, b.alert_threshold)
    if status == "ok":
        return None
    return BudgetAlert(
        category=category, status=status, percent_used=round(spent / b.limit * 100, 1), spent=spent, limit=b.limit
    )


def compute_summary(db: Session, user: User, month: str | None) -> dict:
    start, end, label = month_bounds(month)
    income = f(
        db.scalar(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.user_id == user.id, Transaction.amount > 0, Transaction.date >= start, Transaction.date < end
            )
        )
    )
    cat_spend = spent_by_category(db, user, start, end)
    expenses = f(sum(cat_spend.values()))
    upcoming = f(
        abs(
            float(
                db.scalar(
                    select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                        Transaction.user_id == user.id,
                        Transaction.amount < 0,
                        Transaction.recurring.is_(True),
                        Transaction.date >= start,
                        Transaction.date < end,
                    )
                )
                or 0
            )
        )
    )
    goals_commitment = f(db.scalar(select(func.coalesce(func.sum(Goal.monthly_contribution), 0)).where(Goal.user_id == user.id)))
    balance = total_balance(db, user)
    safe = max(0.0, balance - user.min_reserve - upcoming - goals_commitment)
    last_imported = db.scalar(select(func.max(ImportBatch.created_at)).where(ImportBatch.user_id == user.id))
    return {
        "month": label,
        "balance": balance,
        "income": income,
        "expenses": expenses,
        "savings": f(income - expenses),
        "min_reserve": user.min_reserve,
        "upcoming_recurring": upcoming,
        "goals_commitment": goals_commitment,
        "safe_to_spend": f(safe),
        "last_imported": last_imported,
        "budgets": budgets_for_month(db, user, start, end),
        "category_spending": cat_spend,
    }
