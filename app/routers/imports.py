from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..deps import get_current_user
from ..models import ImportBatch, Transaction, User
from ..schemas import (
    BudgetAlert, ImportBatchOut, ImportCommitIn, ImportCommitOut, ImportPreview, PreviewRow,
)
from ..services.finance import budget_alert_for, get_owned_account, total_balance
from ..services.statement_parser import ParseError, parse_statement

router = APIRouter(prefix="/imports", tags=["statement import"])


@router.post("/preview", response_model=ImportPreview, summary="Parse a statement and preview it (nothing is saved)")
async def preview_import(file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = get_settings()
    content = await file.read(s.max_upload_mb * 1024 * 1024 + 1)
    if len(content) > s.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"File too large. Maximum is {s.max_upload_mb}MB.")
    try:
        result = parse_statement(file.filename or "", content, s.max_import_rows)
    except ParseError as e:
        raise HTTPException(422, str(e)) from e

    dates = [r.date for r in result.rows]
    existing = db.execute(
        select(Transaction.date, Transaction.amount, Transaction.merchant).where(
            Transaction.user_id == user.id, Transaction.date >= min(dates), Transaction.date <= max(dates)
        )
    ).all()
    seen = {(d, round(abs(float(a)), 2), (m or "").strip().lower()) for d, a, m in existing}

    rows = []
    for r in result.rows:
        dup = (r.date, round(abs(r.amount), 2), r.merchant.strip().lower()) in seen
        rows.append(PreviewRow(**r.__dict__, is_duplicate=dup))
    return ImportPreview(
        filename=file.filename or "statement",
        total_rows=len(rows),
        duplicate_count=sum(r.is_duplicate for r in rows),
        needs_review_count=sum(r.needs_review for r in rows),
        skipped_rows=result.skipped,
        warnings=result.warnings,
        rows=rows,
    )


@router.post("/commit", response_model=ImportCommitOut, status_code=201, summary="Save the reviewed rows")
def commit_import(body: ImportCommitIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if len(body.rows) > get_settings().max_import_rows:
        raise HTTPException(413, "Too many rows in one import")
    acc = get_owned_account(db, user, body.account_id)
    batch = ImportBatch(user_id=user.id, account_id=acc.id, filename=body.filename, row_count=len(body.rows))
    db.add(batch)
    db.flush()
    for r in body.rows:
        db.add(
            Transaction(
                user_id=user.id, account_id=acc.id, import_batch_id=batch.id, date=r.date,
                merchant=(r.merchant or "Unknown").strip() or "Unknown", amount=r.amount, category=r.category,
                payment_method=r.payment_method, notes=r.notes,
            )
        )
    db.commit()

    seen: set[tuple[str, str]] = set()
    alerts: list[BudgetAlert] = []
    for r in body.rows:
        key = (r.category, r.date.strftime("%Y-%m"))
        if r.amount < 0 and key not in seen:
            seen.add(key)
            a = budget_alert_for(db, user, r.category, r.date)
            if a:
                alerts.append(a)
    return ImportCommitOut(
        batch=ImportBatchOut.model_validate(batch), imported=len(body.rows), balance=total_balance(db, user), budget_alerts=alerts
    )


@router.get("", response_model=list[ImportBatchOut], summary="Import history")
def list_batches(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(select(ImportBatch).where(ImportBatch.user_id == user.id).order_by(ImportBatch.id.desc())).all()


@router.delete("/{batch_id}", summary="Remove an import and every transaction it created")
def delete_batch(batch_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    batch = db.get(ImportBatch, batch_id)
    if not batch or batch.user_id != user.id:
        raise HTTPException(404, "Import not found")
    deleted = db.query(Transaction).filter(Transaction.import_batch_id == batch.id, Transaction.user_id == user.id).delete()
    db.delete(batch)
    db.commit()
    return {"deleted_transactions": deleted, "balance": total_balance(db, user)}
