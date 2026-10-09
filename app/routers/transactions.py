import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Transaction, User
from ..schemas import TransactionCreate, TransactionCreated, TransactionList, TransactionOut, TransactionUpdate
from ..services.finance import budget_alert_for, get_owned_account, total_balance

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _owned(db: Session, user: User, txn_id: int) -> Transaction:
    txn = db.get(Transaction, txn_id)
    if not txn or txn.user_id != user.id:
        raise HTTPException(404, "Transaction not found")
    return txn


def _filtered(user: User, q, category, account_id, date_from, date_to, type_):
    stmt = select(Transaction).where(Transaction.user_id == user.id)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Transaction.merchant).like(like), func.lower(Transaction.notes).like(like)))
    if category:
        stmt = stmt.where(Transaction.category == category)
    if account_id:
        stmt = stmt.where(Transaction.account_id == account_id)
    if date_from:
        stmt = stmt.where(Transaction.date >= date_from)
    if date_to:
        stmt = stmt.where(Transaction.date <= date_to)
    if type_ == "income":
        stmt = stmt.where(Transaction.amount > 0)
    elif type_ == "expense":
        stmt = stmt.where(Transaction.amount < 0)
    return stmt


@router.get("", response_model=TransactionList)
def list_transactions(
    q: str | None = None,
    category: str | None = None,
    account_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    type: str | None = Query(default=None, pattern="^(income|expense)$"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    base = _filtered(user, q, category, account_id, date_from, date_to, type)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    items = db.scalars(base.order_by(Transaction.date.desc(), Transaction.id.desc()).limit(limit).offset(offset)).all()
    return TransactionList(items=items, total=total, limit=limit, offset=offset)


@router.get("/export", summary="Download all transactions as CSV")
def export_transactions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Transaction).where(Transaction.user_id == user.id).order_by(Transaction.date.desc(), Transaction.id.desc())).all()
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_ALL)
    w.writerow(["Date", "Merchant", "Category", "Payment Method", "Amount", "Notes"])
    for t in rows:
        w.writerow([t.date.isoformat(), t.merchant, t.category, t.payment_method, f"{float(t.amount):.2f}", t.notes])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="finsathi-transactions-{date.today().isoformat()}.csv"'},
    )


@router.post("", response_model=TransactionCreated, status_code=201)
def create_transaction(body: TransactionCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    acc = get_owned_account(db, user, body.account_id)
    txn = Transaction(
        user_id=user.id,
        account_id=acc.id,
        date=body.date or date.today(),
        merchant=(body.merchant or "Unknown").strip() or "Unknown",
        amount=body.amount,
        category=body.category,
        payment_method=body.payment_method,
        notes=body.notes,
        recurring=body.recurring,
    )
    db.add(txn)
    db.commit()
    alert = budget_alert_for(db, user, txn.category, txn.date) if body.amount < 0 else None
    return TransactionCreated(transaction=txn, balance=total_balance(db, user), budget_alert=alert)


@router.get("/{txn_id}", response_model=TransactionOut)
def get_transaction(txn_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _owned(db, user, txn_id)


@router.patch("/{txn_id}", response_model=TransactionOut)
def update_transaction(txn_id: int, body: TransactionUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    txn = _owned(db, user, txn_id)
    data = body.model_dump(exclude_unset=True)
    if "account_id" in data and data["account_id"] is not None:
        txn.account_id = get_owned_account(db, user, data.pop("account_id")).id
    else:
        data.pop("account_id", None)
    for k, v in data.items():
        if v is not None:
            setattr(txn, k, v.strip() if isinstance(v, str) and k == "merchant" else v)
    db.commit()
    return txn


@router.delete("/{txn_id}")
def delete_transaction(txn_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    txn = _owned(db, user, txn_id)
    db.delete(txn)
    db.commit()
    return {"deleted": True, "balance": total_balance(db, user)}
