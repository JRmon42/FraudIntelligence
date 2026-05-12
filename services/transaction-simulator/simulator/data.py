"""Synthetic Nordic card-transaction data generation.

All values are plausible but fully synthetic. PANs are generated with a valid Luhn check
digit but use BIN ranges reserved for testing (4000xxxx).
"""

from __future__ import annotations

import random
import string
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

# Country -> (currency, FX-to-EUR, BIN prefix used for synthetic test cards)
NORDIC_COUNTRIES: dict[str, tuple[str, float, str]] = {
    "SE": ("SEK", 0.087, "400011"),
    "NO": ("NOK", 0.086, "400022"),
    "DK": ("DKK", 0.134, "400033"),
    "FI": ("EUR", 1.000, "400044"),
    "EE": ("EUR", 1.000, "400055"),
}
COUNTRY_WEIGHTS = [0.38, 0.22, 0.18, 0.16, 0.06]  # SE/NO/DK/FI/EE share

# (MCC, label, weight, mean amount EUR, std)
MCC_DISTRIBUTION: list[tuple[str, str, float, float, float]] = [
    ("5411", "grocery_stores", 0.28, 42.0, 18.0),
    ("5812", "eating_places", 0.16, 28.0, 14.0),
    ("5541", "service_stations", 0.10, 55.0, 22.0),
    ("5732", "electronics", 0.05, 320.0, 180.0),
    ("5999", "misc_retail", 0.12, 48.0, 30.0),
    ("4111", "transportation", 0.06, 12.0, 6.0),
    ("7995", "gambling", 0.02, 90.0, 70.0),
    ("5967", "adult_content", 0.005, 35.0, 15.0),
    ("4829", "money_transfer", 0.015, 250.0, 200.0),
    ("5311", "department_stores", 0.08, 75.0, 40.0),
    ("4814", "telecom", 0.04, 25.0, 8.0),
    ("5921", "package_liquor", 0.02, 30.0, 15.0),
    ("5944", "jewelry", 0.005, 480.0, 300.0),
    ("7011", "lodging", 0.02, 180.0, 120.0),
    ("4511", "airlines", 0.025, 280.0, 220.0),
    ("5912", "drug_stores", 0.04, 18.0, 9.0),
]

CHANNELS = ["pos", "ecom", "moto", "atm"]
CHANNEL_WEIGHTS = [0.55, 0.38, 0.02, 0.05]
ENTRY_MODES = {"pos": "chip", "ecom": "ecom", "moto": "manual", "atm": "chip"}


def _luhn_checksum(num: str) -> int:
    digits = [int(d) for d in num]
    odd = digits[-1::-2]
    even = digits[-2::-2]
    total = sum(odd) + sum(sum(divmod(d * 2, 10)) for d in even)
    return (10 - total % 10) % 10


def synth_pan(bin_prefix: str, rng: random.Random) -> str:
    body = bin_prefix + "".join(rng.choices(string.digits, k=15 - len(bin_prefix)))
    return body + str(_luhn_checksum(body + "0"))


@dataclass
class Card:
    pan: str
    country: str
    currency: str
    fx_to_eur: float
    issued_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Merchant:
    merchant_id: str
    name: str
    mcc: str
    country: str
    city: str


@dataclass
class Transaction:
    transaction_id: str
    timestamp: str
    pan: str
    merchant_id: str
    mcc: str
    amount: float
    currency: str
    amount_eur: float
    country: str
    merchant_country: str
    channel: str
    entry_mode: str
    is_cross_border: bool
    label: str = "unknown"

    def to_payload(self) -> dict:
        return {
            "transactionId": self.transaction_id,
            "timestamp": self.timestamp,
            "card": {"pan": self.pan, "country": self.country},
            "merchant": {
                "merchantId": self.merchant_id,
                "mcc": self.mcc,
                "country": self.merchant_country,
            },
            "amount": {
                "value": round(self.amount, 2),
                "currency": self.currency,
                "valueEur": round(self.amount_eur, 2),
            },
            "channel": self.channel,
            "entryMode": self.entry_mode,
            "crossBorder": self.is_cross_border,
            "labelHint": self.label,
        }


NORDIC_CITIES = {
    "SE": ["Stockholm", "Gothenburg", "Malmo", "Uppsala"],
    "NO": ["Oslo", "Bergen", "Trondheim"],
    "DK": ["Copenhagen", "Aarhus", "Odense"],
    "FI": ["Helsinki", "Tampere", "Turku"],
    "EE": ["Tallinn", "Tartu"],
}


def make_card(rng: random.Random, country: str | None = None) -> Card:
    country = country or rng.choices(list(NORDIC_COUNTRIES), weights=COUNTRY_WEIGHTS, k=1)[0]
    currency, fx, bin_prefix = NORDIC_COUNTRIES[country]
    return Card(pan=synth_pan(bin_prefix, rng), country=country, currency=currency, fx_to_eur=fx)


def make_merchant(rng: random.Random, mcc: str | None = None, country: str | None = None) -> Merchant:
    country = country or rng.choices(list(NORDIC_COUNTRIES), weights=COUNTRY_WEIGHTS, k=1)[0]
    if mcc is None:
        mccs = [m[0] for m in MCC_DISTRIBUTION]
        weights = [m[2] for m in MCC_DISTRIBUTION]
        mcc = rng.choices(mccs, weights=weights, k=1)[0]
    return Merchant(
        merchant_id=f"M{rng.randrange(10**8, 10**9)}",
        name=f"merchant-{uuid.uuid4().hex[:8]}",
        mcc=mcc,
        country=country,
        city=rng.choice(NORDIC_CITIES[country]),
    )


def make_normal_transaction(
    rng: random.Random, card: Card, merchant: Merchant, label: str = "normal"
) -> Transaction:
    mcc_row = next(m for m in MCC_DISTRIBUTION if m[0] == merchant.mcc)
    _, _, _, mean, std = mcc_row
    amount_eur = max(0.5, rng.gauss(mean, std))
    if merchant.country in ("FI", "EE"):
        currency = "EUR"
        fx = 1.0
    else:
        currency, fx, _ = NORDIC_COUNTRIES[merchant.country]
    local_amount = amount_eur / fx
    channel = rng.choices(CHANNELS, weights=CHANNEL_WEIGHTS, k=1)[0]
    return Transaction(
        transaction_id=str(uuid.uuid4()),
        timestamp=datetime.now(UTC).isoformat(),
        pan=card.pan,
        merchant_id=merchant.merchant_id,
        mcc=merchant.mcc,
        amount=local_amount,
        currency=currency,
        amount_eur=amount_eur,
        country=card.country,
        merchant_country=merchant.country,
        channel=channel,
        entry_mode=ENTRY_MODES[channel],
        is_cross_border=card.country != merchant.country,
        label=label,
    )


class Population:
    """Pre-warmed pool of cards and merchants for reuse during the run."""

    def __init__(self, rng: random.Random, n_cards: int = 5000, n_merchants: int = 1500) -> None:
        self.rng = rng
        self.cards = [make_card(rng) for _ in range(n_cards)]
        self.merchants = [make_merchant(rng) for _ in range(n_merchants)]

    def random_card(self) -> Card:
        return self.rng.choice(self.cards)

    def random_merchant(self) -> Merchant:
        return self.rng.choice(self.merchants)
