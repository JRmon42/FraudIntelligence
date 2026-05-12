"""Traffic mix profiles producing transactions for each pattern."""

from __future__ import annotations

import random
import time
from collections.abc import Iterator
from typing import Protocol

from simulator.data import (
    Population,
    Transaction,
    make_card,
    make_merchant,
    make_normal_transaction,
)

PATTERNS = ("normal", "fraud-ring", "account-takeover", "mixed")


class Pattern(Protocol):
    name: str

    def __iter__(self) -> Iterator[Transaction]: ...


class NormalPattern:
    name = "normal"

    def __init__(self, population: Population, rng: random.Random) -> None:
        self.pop = population
        self.rng = rng

    def __iter__(self) -> Iterator[Transaction]:
        while True:
            yield make_normal_transaction(self.rng, self.pop.random_card(), self.pop.random_merchant())


class FraudRingPattern:
    """10 cards × 3 merchants × circular flows over a 90 s window.

    Cards rotate through merchants in a deterministic ring; amounts are atypically high for the MCC,
    typically cross-border, and the same card hits each merchant within the window. After 90s a
    fresh ring is rotated in.
    """

    name = "fraud-ring"

    def __init__(self, population: Population, rng: random.Random) -> None:
        self.pop = population
        self.rng = rng
        self._refresh_ring()

    def _refresh_ring(self) -> None:
        countries = ["SE", "NO", "DK", "FI", "EE"]
        self.cards = [make_card(self.rng, country=self.rng.choice(countries)) for _ in range(10)]
        self.merchants = [
            make_merchant(self.rng, mcc="7995"),
            make_merchant(self.rng, mcc="4829"),
            make_merchant(self.rng, mcc="5732"),
        ]
        self.window_start = time.monotonic()
        self.cursor = 0

    def __iter__(self) -> Iterator[Transaction]:
        while True:
            if time.monotonic() - self.window_start > 90.0:
                self._refresh_ring()
            card = self.cards[self.cursor % len(self.cards)]
            merchant = self.merchants[self.cursor % len(self.merchants)]
            tx = make_normal_transaction(self.rng, card, merchant, label="fraud_ring")
            tx.amount_eur *= self.rng.uniform(3.0, 8.0)
            tx.amount = tx.amount_eur  # local currency recomputed coarsely
            tx.is_cross_border = card.country != merchant.country
            self.cursor += 1
            yield tx


class AccountTakeoverPattern:
    """A single card suddenly bursts a high-velocity series of e-commerce purchases."""

    name = "account-takeover"

    def __init__(self, population: Population, rng: random.Random) -> None:
        self.pop = population
        self.rng = rng
        self._refresh_victim()

    def _refresh_victim(self) -> None:
        self.victim = self.pop.random_card()
        self.burst_remaining = self.rng.randint(8, 25)

    def __iter__(self) -> Iterator[Transaction]:
        while True:
            if self.burst_remaining <= 0:
                self._refresh_victim()
            merchant = make_merchant(self.rng, mcc=self.rng.choice(["5732", "5944", "5999"]))
            tx = make_normal_transaction(self.rng, self.victim, merchant, label="account_takeover")
            tx.channel = "ecom"
            tx.entry_mode = "ecom"
            tx.amount_eur *= self.rng.uniform(1.5, 4.0)
            self.burst_remaining -= 1
            yield tx


class MixedPattern:
    """90 % normal, 7 % ATO, 3 % ring — weighted random selection per request."""

    name = "mixed"

    def __init__(self, population: Population, rng: random.Random) -> None:
        self.rng = rng
        self.normal = iter(NormalPattern(population, rng))
        self.ato = iter(AccountTakeoverPattern(population, rng))
        self.ring = iter(FraudRingPattern(population, rng))

    def __iter__(self) -> Iterator[Transaction]:
        while True:
            r = self.rng.random()
            if r < 0.90:
                yield next(self.normal)
            elif r < 0.97:
                yield next(self.ato)
            else:
                yield next(self.ring)


def build(pattern: str, population: Population, rng: random.Random) -> Pattern:
    pattern = pattern.lower()
    if pattern == "normal":
        return NormalPattern(population, rng)
    if pattern == "fraud-ring":
        return FraudRingPattern(population, rng)
    if pattern == "account-takeover":
        return AccountTakeoverPattern(population, rng)
    if pattern == "mixed":
        return MixedPattern(population, rng)
    raise ValueError(f"Unknown pattern: {pattern!r}. Choose one of {PATTERNS}.")
