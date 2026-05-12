import random
from itertools import islice

import pytest

from simulator import patterns
from simulator.data import Population


@pytest.fixture()
def population():
    return Population(random.Random(42), n_cards=100, n_merchants=30)


@pytest.mark.parametrize("name", patterns.PATTERNS)
def test_pattern_emits_transactions(name, population):
    rng = random.Random(123)
    p = patterns.build(name, population, rng)
    txs = list(islice(iter(p), 20))
    assert len(txs) == 20
    assert all(t.transaction_id for t in txs)
    assert all(t.amount_eur > 0 for t in txs)


def test_fraud_ring_uses_only_ring_cards(population):
    rng = random.Random(7)
    p = patterns.build("fraud-ring", population, rng)
    txs = list(islice(iter(p), 60))
    distinct_cards = {t.pan for t in txs}
    distinct_merchants = {t.merchant_id for t in txs}
    assert len(distinct_cards) <= 10
    assert len(distinct_merchants) <= 3
    assert all(t.label == "fraud_ring" for t in txs)


def test_account_takeover_high_velocity_single_card(population):
    rng = random.Random(11)
    p = patterns.build("account-takeover", population, rng)
    txs = list(islice(iter(p), 8))
    assert len({t.pan for t in txs}) == 1
    assert all(t.channel == "ecom" for t in txs)


def test_unknown_pattern_raises(population):
    with pytest.raises(ValueError):
        patterns.build("nope", population, random.Random(0))
