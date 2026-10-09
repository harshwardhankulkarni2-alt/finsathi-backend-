from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Account, ImportBatch, Transaction, User
from ..schemas import AccountCreate, AccountOut, AccountUpdate
from ..services.finance import account_balance, get_owned_account

router = APIRouter(prefix="/accounts", tags=["accounts"])


def _out(db: Session, acc: Account) -> AccountOut:
    count = db.scalar(select(func.count(Transaction.id)).where(Transaction.account_id == acc.id)) or 0
    return AccountOut(
        id=acc.id,
        name=acc.name,
        starting_balance=float(acc.starting_balance or 0),
        as_of=acc.as_of,
        current_balance=account_balance(db, acc),
        transaction_count=count,
    )


@router.get("", response_model=list[AccountOut])
def list_accounts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    accounts = db.scalars(select(Account).where(Account.user_id == user.id).order_by(Account.id)).all()
    return [_out(db, a) for a in accounts]


@router.post("", response_model=AccountOut, status_code=201)
def create_account(body: AccountCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    kwargs = {"as_of": body.as_of} if body.as_of else {}
    acc = Account(user_id=user.id, name=body.name.strip(), starting_balance=body.starting_balance, **kwargs)
    db.add(acc)
    db.commit()
    return _out(db, acc)


@router.get("/{account_id}", response_model=AccountOut)
def get_account(account_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _out(db, get_owned_account(db, user, account_id))


@router.patch("/{account_id}", response_model=AccountOut)
def update_account(account_id: int, body: AccountUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    acc = get_owned_account(db, user, account_id)
    if body.name is not None:
        acc.name = body.name.strip()
    if body.starting_balance is not None:
        acc.starting_balance = body.starting_balance
    if body.as_of is not None:
        acc.as_of = body.as_of
    db.commit()
    return _out(db, acc)


@router.delete("/{account_id}", status_code=204)
def delete_account(account_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    acc = get_owned_account(db, user, account_id)
    n = db.scalar(select(func.count(Account.id)).where(Account.user_id == user.id)) or 0
    if n <= 1:
        raise HTTPException(400, "You can't delete your only account")
    db.query(Transaction).filter(Transaction.account_id == account_id).delete()
    db.query(ImportBatch).filter(ImportBatch.account_id == account_id).delete()
    db.delete(acc)
    db.commit()
