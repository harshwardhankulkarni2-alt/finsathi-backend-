import io
from datetime import date

from openpyxl import Workbook

from .conftest import signup

TODAY = date.today().isoformat()
MONTH = date.today().strftime("%Y-%m")


def add(client, auth, **kw):
    body = {"amount": 500, "type": "expense", "category": "Food", "merchant": "Swiggy", **kw}
    r = client.post("/api/transactions", json=body, headers=auth)
    assert r.status_code == 201, r.text
    return r.json()


# ---------------- auth ----------------
def test_signup_login_me(client):
    h = signup(client)
    r = client.post("/api/auth/login", json={"email": "A@Example.com", "password": "password123"})
    assert r.status_code == 200 and r.json()["user"]["email"] == "a@example.com"
    assert client.get("/api/auth/me", headers=h).json()["name"] == "Aarav"


def test_duplicate_email_and_bad_login(client):
    signup(client)
    assert client.post("/api/auth/signup", json={"name": "X", "email": "a@example.com", "password": "password123"}).status_code == 409
    assert client.post("/api/auth/login", json={"email": "a@example.com", "password": "wrong-pass"}).status_code == 401
    assert client.post("/api/auth/signup", json={"name": "X", "email": "b@example.com", "password": "short"}).status_code == 422


def test_requires_auth(client):
    assert client.get("/api/transactions").status_code == 401
    assert client.get("/api/summary", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_swagger_form_login(client):
    signup(client)
    r = client.post("/api/auth/token", data={"username": "a@example.com", "password": "password123"})
    assert r.status_code == 200 and r.json()["token_type"] == "bearer"


# ---------------- accounts / balance ----------------
def test_balance_follows_transactions(client, auth):
    accs = client.get("/api/accounts", headers=auth).json()
    assert accs[0]["current_balance"] == 10000
    r = add(client, auth, amount=420)
    assert r["balance"] == 9580 and r["transaction"]["amount"] == -420
    r = add(client, auth, amount=5000, type="income", category="Income", merchant="Salary")
    assert r["balance"] == 14580
    # editing the starting balance moves the current balance
    client.patch(f"/api/accounts/{accs[0]['id']}", json={"starting_balance": 0}, headers=auth)
    assert client.get("/api/accounts", headers=auth).json()[0]["current_balance"] == 4580


def test_second_account_and_delete_rules(client, auth):
    first = client.get("/api/accounts", headers=auth).json()[0]
    assert client.delete(f"/api/accounts/{first['id']}", headers=auth).status_code == 400  # only account
    second = client.post("/api/accounts", json={"name": "Savings", "starting_balance": 2000}, headers=auth).json()
    add(client, auth, account_id=second["id"], amount=100)
    assert client.delete(f"/api/accounts/{second['id']}", headers=auth).status_code == 204
    assert len(client.get("/api/accounts", headers=auth).json()) == 1


# ---------------- transactions ----------------
def test_transaction_crud_filters(client, auth):
    t = add(client, auth, amount=300, merchant="Uber", category="Transport")["transaction"]
    add(client, auth, amount=100, merchant="Zomato")
    assert client.get("/api/transactions", headers=auth).json()["total"] == 2
    assert client.get("/api/transactions?q=uber", headers=auth).json()["total"] == 1
    assert client.get("/api/transactions?category=Food", headers=auth).json()["total"] == 1
    assert client.get("/api/transactions?type=income", headers=auth).json()["total"] == 0
    r = client.patch(f"/api/transactions/{t['id']}", json={"amount": -350, "category": "Other"}, headers=auth)
    assert r.json()["amount"] == -350 and r.json()["category"] == "Other"
    d = client.delete(f"/api/transactions/{t['id']}", headers=auth).json()
    assert d["deleted"] and d["balance"] == 9900
    assert client.get(f"/api/transactions/{t['id']}", headers=auth).status_code == 404


def test_transaction_validation(client, auth):
    bad = {"amount": 0, "category": "Food"}
    assert client.post("/api/transactions", json=bad, headers=auth).status_code == 422
    assert client.post("/api/transactions", json={"amount": 5, "category": "Nope"}, headers=auth).status_code == 422
    assert client.post("/api/transactions", json={"amount": 5, "category": "Food", "payment_method": "Bitcoin"}, headers=auth).status_code == 422


def test_users_are_isolated(client, auth):
    t = add(client, auth)["transaction"]
    other = signup(client, email="b@example.com")
    assert client.get(f"/api/transactions/{t['id']}", headers=other).status_code == 404
    assert client.delete(f"/api/transactions/{t['id']}", headers=other).status_code == 404
    assert client.get("/api/transactions", headers=other).json()["total"] == 0
    acc_id = client.get("/api/accounts", headers=auth).json()[0]["id"]
    assert client.get(f"/api/accounts/{acc_id}", headers=other).status_code == 404


def test_export_csv(client, auth):
    add(client, auth, merchant='Cafe "Mocha", Pune')
    r = client.get("/api/transactions/export", headers=auth)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert 'Cafe ""Mocha"", Pune' in r.text and r.text.startswith('"Date"')


# ---------------- budgets / summary ----------------
def test_budget_alerts_and_spent(client, auth):
    client.put("/api/budgets/Food", json={"limit": 1000, "alert_threshold": 80}, headers=auth)
    assert add(client, auth, amount=500)["budget_alert"] is None
    a = add(client, auth, amount=350)["budget_alert"]
    assert a["status"] == "warning" and a["percent_used"] == 85.0
    a = add(client, auth, amount=300)["budget_alert"]
    assert a["status"] == "exceeded"
    food = next(b for b in client.get(f"/api/budgets?month={MONTH}", headers=auth).json() if b["category"] == "Food")
    assert food["spent"] == 1150 and food["status"] == "exceeded" and food["remaining"] == -150


def test_budget_validation_and_delete(client, auth):
    assert client.put("/api/budgets/Income", json={"limit": 5}, headers=auth).status_code == 422
    assert client.put("/api/budgets/Food", json={"limit": -5}, headers=auth).status_code == 422
    assert client.delete("/api/budgets/Food", headers=auth).status_code == 204
    assert client.delete("/api/budgets/Food", headers=auth).status_code == 404
    assert client.get("/api/summary?month=2026-13", headers=auth).status_code == 422


def test_summary_and_safe_to_spend(client, auth):
    add(client, auth, amount=30000, type="income", category="Income", merchant="Salary")
    add(client, auth, amount=2000, category="Bills", merchant="Rent", recurring=True)
    add(client, auth, amount=1000, category="Food")
    client.post("/api/goals", json={"name": "Laptop", "target": 60000, "monthly_contribution": 6000}, headers=auth)
    s = client.get("/api/summary", headers=auth).json()
    assert s["balance"] == 10000 + 30000 - 3000
    assert s["income"] == 30000 and s["expenses"] == 3000 and s["savings"] == 27000
    assert s["upcoming_recurring"] == 2000 and s["goals_commitment"] == 6000
    # same formula as the frontend: balance - reserve - recurring - goals
    assert s["safe_to_spend"] == 37000 - 5000 - 2000 - 6000
    assert s["category_spending"] == {"Bills": 2000.0, "Food": 1000.0}
    client.patch("/api/auth/me", json={"min_reserve": 1000}, headers=auth)
    assert client.get("/api/summary", headers=auth).json()["safe_to_spend"] == 37000 - 1000 - 2000 - 6000


def test_safe_to_spend_never_negative(client):
    h = signup(client, email="poor@example.com", starting_balance=0)
    assert client.get("/api/summary", headers=h).json()["safe_to_spend"] == 0


# ---------------- goals ----------------
def test_goals_crud(client, auth):
    g = client.post("/api/goals", json={"name": "Trip", "target": 1000, "current": 250}, headers=auth).json()
    assert g["percent_complete"] == 25
    g = client.post(f"/api/goals/{g['id']}/contribute", json={"amount": 250}, headers=auth).json()
    assert g["current"] == 500 and g["percent_complete"] == 50
    g = client.patch(f"/api/goals/{g['id']}", json={"target": 500}, headers=auth).json()
    assert g["percent_complete"] == 100
    assert client.delete(f"/api/goals/{g['id']}", headers=auth).status_code == 204
    assert client.get("/api/goals", headers=auth).json() == []
    assert client.post("/api/goals/999/contribute", json={"amount": 5}, headers=auth).status_code == 404


# ---------------- statement import ----------------
CSV_BASIC = (
    "Date,Description,Amount\n"
    f"{TODAY},Swiggy Order,-420\n"
    f"{TODAY},Salary Credit,35000\n"
    f"{TODAY},Mystery Shop,-99\n"
)

CSV_BANK_STYLE = (
    "Account Statement for A/C XXXX1234\n"
    "Period: 01/09/2026 to 30/09/2026\n"
    "\n"
    "Txn Date,Value Date,Narration,Withdrawal Amt.,Deposit Amt.,Closing Balance\n"
    '02/09/2026,02/09/2026,UPI/123456789/Swiggy/swiggy@icici,"1,420.50",,"8,579.50"\n'
    '03/09/2026,03/09/2026,UPI/987654321/Uber India/uber@axis,280.00,,"8,299.50"\n'
    '05/09/2026,05/09/2026,NEFT-SALARY ACME LTD,,"35,000.00","43,299.50"\n'
    "Total,,,,,\n"
)


def upload(client, auth, name, data: bytes):
    return client.post("/api/imports/preview", files={"file": (name, data)}, headers=auth)


def test_preview_basic_csv(client, auth):
    r = upload(client, auth, "s.csv", CSV_BASIC.encode())
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["total_rows"] == 3 and p["duplicate_count"] == 0
    cats = {row["merchant"]: row["category"] for row in p["rows"]}
    assert cats == {"Swiggy Order": "Food", "Salary Credit": "Income", "Mystery Shop": "Other"}
    assert p["needs_review_count"] == 1
    assert client.get("/api/transactions", headers=auth).json()["total"] == 0  # preview saves nothing


def test_preview_bank_style_with_preamble_and_debit_credit(client, auth):
    p = upload(client, auth, "hdfc.csv", CSV_BANK_STYLE.encode()).json()
    assert p["total_rows"] == 3 and p["skipped_rows"] == 1  # "Total" footer skipped
    by = {r["merchant"]: r for r in p["rows"]}
    assert by["Swiggy"]["amount"] == -1420.5 and by["Swiggy"]["category"] == "Food" and by["Swiggy"]["payment_method"] == "UPI"
    assert by["Uber India"]["category"] == "Transport"
    salary = next(r for r in p["rows"] if r["amount"] > 0)
    assert salary["amount"] == 35000 and salary["category"] == "Income" and salary["date"] == "2026-09-05"


def test_preview_xlsx(client, auth):
    wb = Workbook()
    ws = wb.active
    ws.append(["Date", "Particulars", "Debit", "Credit"])
    ws.append([date(2026, 9, 2), "Zomato", 350, None])
    ws.append([date(2026, 9, 3), "Refund", None, 100])
    buf = io.BytesIO()
    wb.save(buf)
    p = upload(client, auth, "s.xlsx", buf.getvalue()).json()
    assert [r["amount"] for r in p["rows"]] == [-350, 100]
    assert p["rows"][0]["category"] == "Food"


def test_preview_errors(client, auth):
    assert upload(client, auth, "a.pdf", b"%PDF").status_code == 422
    assert upload(client, auth, "a.exe", b"x").status_code == 422
    assert upload(client, auth, "a.csv", b"").status_code == 422
    assert upload(client, auth, "a.csv", b"foo,bar\n1,2\n").status_code == 422
    assert upload(client, auth, "a.xlsx", b"not really excel").status_code == 422
    assert client.post("/api/imports/preview", files={"file": ("a.csv", b"x")}).status_code == 401


def test_commit_flow_duplicates_and_delete(client, auth):
    rows = upload(client, auth, "s.csv", CSV_BASIC.encode()).json()["rows"]
    keep = [{k: r[k] for k in ("date", "merchant", "amount", "category", "payment_method", "notes")} for r in rows]
    c = client.post("/api/imports/commit", json={"filename": "s.csv", "rows": keep}, headers=auth)
    assert c.status_code == 201, c.text
    out = c.json()
    assert out["imported"] == 3 and out["balance"] == 10000 - 420 + 35000 - 99
    batch_id = out["batch"]["id"]

    # re-uploading the same file flags everything as duplicate
    again = upload(client, auth, "s.csv", CSV_BASIC.encode()).json()
    assert again["duplicate_count"] == 3 and all(r["is_duplicate"] for r in again["rows"])

    assert len(client.get("/api/imports", headers=auth).json()) == 1
    assert client.get("/api/summary", headers=auth).json()["last_imported"] is not None

    d = client.delete(f"/api/imports/{batch_id}", headers=auth).json()
    assert d["deleted_transactions"] == 3 and d["balance"] == 10000
    assert client.get("/api/transactions", headers=auth).json()["total"] == 0
    assert client.delete(f"/api/imports/{batch_id}", headers=auth).status_code == 404


def test_commit_validation_and_isolation(client, auth):
    assert client.post("/api/imports/commit", json={"rows": []}, headers=auth).status_code == 422
    bad = {"rows": [{"date": TODAY, "merchant": "x", "amount": 0, "category": "Food"}]}
    assert client.post("/api/imports/commit", json=bad, headers=auth).status_code == 422
    other = signup(client, email="b@example.com")
    acc_id = client.get("/api/accounts", headers=auth).json()[0]["id"]
    ok = {"account_id": acc_id, "rows": [{"date": TODAY, "merchant": "x", "amount": -5, "category": "Food"}]}
    assert client.post("/api/imports/commit", json=ok, headers=other).status_code == 404


def test_commit_returns_budget_alerts(client, auth):
    client.put("/api/budgets/Food", json={"limit": 100}, headers=auth)
    rows = [{"date": TODAY, "merchant": "Pizza", "amount": -150, "category": "Food"}]
    out = client.post("/api/imports/commit", json={"rows": rows}, headers=auth).json()
    assert out["budget_alerts"][0]["category"] == "Food" and out["budget_alerts"][0]["status"] == "exceeded"


# ---------------- assistant / insights / sync / meta ----------------
def test_assistant_and_insights(client, auth):
    add(client, auth, amount=30000, type="income", category="Income", merchant="Salary")
    add(client, auth, amount=9000, category="Food")  # exceeds default Food budget (8000)
    r = client.post("/api/assistant", json={"message": "What's my safe to spend?"}, headers=auth).json()["reply"]
    assert "Safe-to-Spend" in r and "₹" in r
    assert "Food" in client.post("/api/assistant", json={"message": "any budget over limit?"}, headers=auth).json()["reply"]
    assert client.post("/api/assistant", json={"message": "hello"}, headers=auth).status_code == 200
    ins = client.get("/api/insights", headers=auth).json()
    assert any("Food budget exceeded" == i["title"] for i in ins)


def test_sync_placeholder_and_health(client, auth):
    r = client.post("/api/sync", headers=auth)
    assert r.status_code == 501 and r.json()["status"] == "not_implemented"
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/openapi.json").status_code == 200
