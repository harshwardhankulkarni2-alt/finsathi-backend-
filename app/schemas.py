from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from .constants import ALL_CATEGORIES, PAYMENT_METHODS


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- auth ----------
class SignupIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    starting_balance: float = Field(default=0, ge=-1e9, le=1e12)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(ORM):
    id: int
    name: str
    email: EmailStr
    min_reserve: float


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    min_reserve: float | None = Field(default=None, ge=0)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- accounts ----------
class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    starting_balance: float = 0
    as_of: dt.date | None = None


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    starting_balance: float | None = None
    as_of: dt.date | None = None


class AccountOut(BaseModel):
    id: int
    name: str
    starting_balance: float
    as_of: dt.date
    current_balance: float
    transaction_count: int


# ---------- transactions ----------
def _check_category(v: str) -> str:
    if v not in ALL_CATEGORIES:
        raise ValueError(f"category must be one of {ALL_CATEGORIES}")
    return v


def _check_payment(v: str) -> str:
    if v not in PAYMENT_METHODS:
        raise ValueError(f"payment_method must be one of {PAYMENT_METHODS}")
    return v


class TransactionCreate(BaseModel):
    """Send a signed `amount` (negative = expense), OR a positive `amount` with `type`."""

    amount: float = Field(ge=-1e12, le=1e12)
    type: Literal["expense", "income"] | None = None
    category: str
    merchant: str = Field(default="Unknown", max_length=255)
    payment_method: str = "UPI"
    date: dt.date | None = None
    notes: str = Field(default="", max_length=500)
    recurring: bool = False
    account_id: int | None = None

    _cat = field_validator("category")(_check_category)
    _pay = field_validator("payment_method")(_check_payment)

    @model_validator(mode="after")
    def _signed(self):
        if self.amount == 0:
            raise ValueError("amount cannot be 0")
        if self.type == "expense":
            self.amount = -abs(self.amount)
        elif self.type == "income":
            self.amount = abs(self.amount)
        return self


class TransactionUpdate(BaseModel):
    amount: float | None = Field(default=None, ge=-1e12, le=1e12)
    category: str | None = None
    merchant: str | None = Field(default=None, max_length=255)
    payment_method: str | None = None
    date: dt.date | None = None
    notes: str | None = Field(default=None, max_length=500)
    recurring: bool | None = None
    account_id: int | None = None

    @field_validator("category")
    @classmethod
    def _c(cls, v):
        return v if v is None else _check_category(v)

    @field_validator("payment_method")
    @classmethod
    def _p(cls, v):
        return v if v is None else _check_payment(v)

    @field_validator("amount")
    @classmethod
    def _a(cls, v):
        if v == 0:
            raise ValueError("amount cannot be 0")
        return v


class TransactionOut(ORM):
    id: int
    account_id: int
    import_batch_id: int | None
    date: dt.date
    merchant: str
    amount: float
    category: str
    payment_method: str
    notes: str
    recurring: bool


class BudgetAlert(BaseModel):
    category: str
    status: Literal["warning", "exceeded"]
    percent_used: float
    spent: float
    limit: float


class TransactionCreated(BaseModel):
    transaction: TransactionOut
    balance: float
    budget_alert: BudgetAlert | None = None


class TransactionList(BaseModel):
    items: list[TransactionOut]
    total: int
    limit: int
    offset: int


# ---------- budgets ----------
class BudgetIn(BaseModel):
    limit: float = Field(gt=0, le=1e12)
    alert_threshold: int = Field(default=80, ge=1, le=100)


class BudgetOut(BaseModel):
    category: str
    limit: float
    alert_threshold: int
    spent: float
    remaining: float
    percent_used: float
    status: Literal["ok", "warning", "exceeded"]


# ---------- goals ----------
class GoalCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    icon: str = Field(default="Target", max_length=40)
    target: float = Field(gt=0, le=1e12)
    current: float = Field(default=0, ge=0)
    target_date: str = Field(default="", max_length=40)
    monthly_contribution: float = Field(default=0, ge=0)


class GoalUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    icon: str | None = Field(default=None, max_length=40)
    target: float | None = Field(default=None, gt=0, le=1e12)
    current: float | None = Field(default=None, ge=0)
    target_date: str | None = Field(default=None, max_length=40)
    monthly_contribution: float | None = Field(default=None, ge=0)


class GoalOut(ORM):
    id: int
    name: str
    icon: str
    target: float
    current: float
    target_date: str
    monthly_contribution: float
    percent_complete: float = 0


class ContributeIn(BaseModel):
    amount: float = Field(gt=0, le=1e12)


# ---------- imports ----------
class PreviewRow(BaseModel):
    date: dt.date
    merchant: str
    amount: float
    category: str
    payment_method: str
    notes: str = ""
    is_duplicate: bool = False
    needs_review: bool = False


class ImportPreview(BaseModel):
    filename: str
    total_rows: int
    duplicate_count: int
    needs_review_count: int
    skipped_rows: int
    warnings: list[str]
    rows: list[PreviewRow]


class CommitRow(BaseModel):
    date: dt.date
    merchant: str = Field(max_length=255)
    amount: float
    category: str
    payment_method: str = "Bank Transfer"
    notes: str = Field(default="", max_length=500)

    _cat = field_validator("category")(_check_category)
    _pay = field_validator("payment_method")(_check_payment)

    @field_validator("amount")
    @classmethod
    def _a(cls, v):
        if v == 0:
            raise ValueError("amount cannot be 0")
        return v


class ImportCommitIn(BaseModel):
    filename: str = Field(default="statement", max_length=255)
    account_id: int | None = None
    rows: list[CommitRow] = Field(min_length=1)


class ImportBatchOut(ORM):
    id: int
    account_id: int
    filename: str
    row_count: int
    created_at: dt.datetime


class ImportCommitOut(BaseModel):
    batch: ImportBatchOut
    imported: int
    balance: float
    budget_alerts: list[BudgetAlert]


# ---------- summary / assistant ----------
class SummaryOut(BaseModel):
    month: str
    balance: float
    income: float
    expenses: float
    savings: float
    min_reserve: float
    upcoming_recurring: float
    goals_commitment: float
    safe_to_spend: float
    last_imported: dt.datetime | None
    budgets: list[BudgetOut]
    category_spending: dict[str, float]


class AssistantIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


class AssistantOut(BaseModel):
    reply: str


class Insight(BaseModel):
    kind: Literal["info", "warning", "success"]
    title: str
    body: str
