import re

from ..constants import PAYMENT_METHODS

CATEGORY_KEYWORDS = {
    "Food": ["swiggy", "zomato", "blinkit", "zepto", "cafe", "restaurant", "bigbasket", "dominos", "domino",
             "starbucks", "eatery", "mcdonald", "kfc", "pizza", "bakery", "grocery", "dmart", "instamart"],
    "Transport": ["uber", "ola", "rapido", "metro", "fuel", "petrol", "irctc", "diesel", "redbus",
                  "fastag", "parking", "indigo", "airindia", "railway"],
    "Shopping": ["amazon", "flipkart", "myntra", "ajio", "reliance trends", "mall", "meesho", "nykaa", "decathlon"],
    "Entertainment": ["netflix", "spotify", "prime video", "hotstar", "pvr", "bookmyshow", "inox", "youtube",
                      "sonyliv", "zee5", "gaming"],
    "Bills": ["electricity", "broadband", "wifi", "rent", "landlord", "gas board", "water bill", "recharge",
              "dth", "airtel", "jio", "vodafone", "bsnl", "insurance", "lic ", "emi", "maintenance"],
    "Education": ["coursera", "udemy", "byju", "school", "college", "tuition", "exam", "university", "unacademy",
                  "fees", "library"],
    "Health": ["pharmacy", "hospital", "apollo", "clinic", "diagnostic", "medicos", "medplus", "pharmeasy",
               "1mg", "dental", "doctor"],
}

INCOME_KEYWORDS = ["salary", "stipend", "interest credit", "refund", "cashback", "dividend", "freelance"]


def guess_category(text: str, amount: float) -> tuple[str, bool]:
    """Returns (category, needs_review). Income is always 'Income'."""
    if amount > 0:
        return "Income", False
    t = (text or "").lower()
    for cat, words in CATEGORY_KEYWORDS.items():
        if any(w in t for w in words):
            return cat, False
    return "Other", True


def guess_payment_method(text: str, fallback: str | None = None) -> str:
    t = (text or "").lower()
    if fallback and fallback in PAYMENT_METHODS:
        return fallback
    if t.startswith("upi") or "/upi/" in t or "upi-" in t:
        return "UPI"
    if re.search(r"\b(neft|imps|rtgs)\b", t):
        return "Bank Transfer"
    if re.search(r"\b(atm|cash)\b", t):
        return "Cash"
    if re.search(r"\b(pos|debit card)\b", t):
        return "Debit Card"
    if "credit card" in t or "cc " in t:
        return "Credit Card"
    return "Bank Transfer"
