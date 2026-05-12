import random

from simulator.data import (
    NORDIC_COUNTRIES,
    Population,
    _luhn_checksum,
    make_card,
    make_merchant,
    make_normal_transaction,
    synth_pan,
)


def test_luhn_pan_is_valid():
    rng = random.Random(0)
    pan = synth_pan("400011", rng)
    assert len(pan) == 16
    digits = [int(d) for d in pan]
    s = 0
    for i, d in enumerate(reversed(digits)):
        s += d if i % 2 == 0 else sum(divmod(d * 2, 10))
    assert s % 10 == 0


def test_luhn_checksum_deterministic():
    assert _luhn_checksum("79927398710") == _luhn_checksum("79927398710")


def test_make_card_uses_known_country():
    rng = random.Random(1)
    card = make_card(rng)
    assert card.country in NORDIC_COUNTRIES
    assert card.currency == NORDIC_COUNTRIES[card.country][0]


def test_population_pool_shapes():
    pop = Population(random.Random(2), n_cards=20, n_merchants=10)
    assert len(pop.cards) == 20
    assert len(pop.merchants) == 10
    assert pop.random_card() in pop.cards
    assert pop.random_merchant() in pop.merchants


def test_normal_transaction_payload_shape():
    rng = random.Random(3)
    card = make_card(rng, country="SE")
    merchant = make_merchant(rng, mcc="5411", country="SE")
    tx = make_normal_transaction(rng, card, merchant)
    payload = tx.to_payload()
    assert payload["transactionId"] == tx.transaction_id
    assert payload["card"]["pan"] == card.pan
    assert payload["amount"]["currency"] == "SEK"
    assert payload["crossBorder"] is False
