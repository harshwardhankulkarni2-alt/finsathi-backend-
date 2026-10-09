"""Seam for future automatic bank sync (mirrors FinancialDataService.syncTransactions in the frontend).

NOT IMPLEMENTED. A real implementation would use an *authorized* financial-data provider
(e.g. an RBI Account Aggregator) with user consent. Finsathi never scrapes Paytm / PhonePe /
Google Pay / bank sites and never asks for banking passwords.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class FinancialDataProvider(ABC):
    name: str

    @abstractmethod
    def fetch_transactions(self, user_id: int, since: str | None = None) -> list[dict]:
        """Return normalized transaction dicts (same shape as the statement-import rows)."""


class NotImplementedProvider(FinancialDataProvider):
    name = "none"

    def fetch_transactions(self, user_id: int, since: str | None = None) -> list[dict]:
        raise NotImplementedError("Automatic sync is not available yet.")


def get_provider() -> FinancialDataProvider:
    return NotImplementedProvider()
