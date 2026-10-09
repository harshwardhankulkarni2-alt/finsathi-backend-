"""Rule-based insights + assistant answers built from the user's real data.

No external AI service is called. Swap `answer()` for an LLM call later if wanted.
"""
from __future__ import annotations

from ..schemas import Insight


def inr(x: float) -> str:
    neg = x < 0
    s = f"{abs(x):.0f}"
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return f"{'-' if neg else ''}₹{s}"


def build_insights(summary: dict, goals: list) -> list[Insight]:
    out: list[Insight] = []
    for b in summary["budgets"]:
        if b.status == "exceeded":
            out.append(Insight(kind="warning", title=f"{b.category} budget exceeded",
                               body=f"You've spent {inr(b.spent)} of your {inr(b.limit)} {b.category} budget this month."))
        elif b.status == "warning":
            out.append(Insight(kind="warning", title=f"{b.category} budget at {b.percent_used:.0f}%",
                               body=f"Only {inr(b.remaining)} left in {b.category} for this month."))
    spend = summary["category_spending"]
    if spend:
        top = max(spend, key=spend.get)
        out.append(Insight(kind="info", title=f"Top spending: {top}",
                           body=f"{top} is your biggest category this month at {inr(spend[top])}."))
    if summary["income"] > 0:
        rate = summary["savings"] / summary["income"] * 100
        kind = "success" if rate >= 20 else "info"
        out.append(Insight(kind=kind, title=f"Savings rate {rate:.0f}%",
                           body=f"You saved {inr(summary['savings'])} of {inr(summary['income'])} income this month."))
    for g in goals:
        remaining = g.target - g.current
        if remaining > 0 and g.monthly_contribution > 0:
            months = -(-remaining // g.monthly_contribution)
            out.append(Insight(kind="info", title=f"Goal: {g.name}",
                               body=f"At {inr(g.monthly_contribution)}/month you'll reach {inr(g.target)} in about {int(months)} month(s)."))
    if summary["safe_to_spend"] <= 0:
        out.append(Insight(kind="warning", title="Safe-to-Spend is ₹0",
                           body="After your reserve, recurring bills and goal contributions, there's nothing safe to spend right now."))
    return out


def answer(message: str, summary: dict, goals: list) -> str:
    m = message.lower()
    if any(k in m for k in ("safe", "can i spend", "afford")):
        return (f"Your Safe-to-Spend is {inr(summary['safe_to_spend'])}. That's your balance of {inr(summary['balance'])} "
                f"minus a {inr(summary['min_reserve'])} reserve, {inr(summary['upcoming_recurring'])} of recurring bills "
                f"and {inr(summary['goals_commitment'])} of monthly goal contributions.")
    if "balance" in m:
        return f"Your current balance is {inr(summary['balance'])}."
    if any(k in m for k in ("budget", "over", "limit")):
        bad = [b for b in summary["budgets"] if b.status != "ok"]
        if not bad:
            return "All your budgets are on track this month. 👍"
        return "Watch these budgets: " + "; ".join(f"{b.category} ({b.percent_used:.0f}% used)" for b in bad) + "."
    if any(k in m for k in ("spent", "spend", "expense", "biggest", "most")):
        spend = summary["category_spending"]
        if not spend:
            return "You haven't recorded any expenses this month yet."
        top = max(spend, key=spend.get)
        return f"You've spent {inr(summary['expenses'])} this month. Your biggest category is {top} at {inr(spend[top])}."
    if any(k in m for k in ("income", "earn", "salary")):
        return f"You've received {inr(summary['income'])} this month."
    if any(k in m for k in ("save", "saving")):
        return f"You've saved {inr(summary['savings'])} this month (income {inr(summary['income'])} − expenses {inr(summary['expenses'])})."
    if "goal" in m:
        if not goals:
            return "You don't have any goals yet. Add one on the Goals page."
        return "Your goals: " + "; ".join(f"{g.name} {inr(g.current)}/{inr(g.target)}" for g in goals) + "."
    return ("I can answer questions about your balance, Safe-to-Spend, budgets, spending, income, savings and goals. "
            "Try: “What's my safe to spend?”")
